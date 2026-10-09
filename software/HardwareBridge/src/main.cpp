// CYOBot hardware endpoint: no gait, model, web server, or autonomous sweep.
#include <Arduino.h>
#include <Wire.h>
#include <WiFi.h>
#include <Adafruit_NeoPixel.h>
#include <esp_task_wdt.h>
#include <lwip/sockets.h>
#include <fcntl.h>
#include "protocol.h"
#include "wifi_config.h"
#include "media_bridge.h"
using namespace cyo;

static constexpr uint8_t PCA=0x43, IMU=0x6A;
static int sock=-1;
static uint8_t mac[6];
static uint32_t bootId, challenge, session=0, lastCommand=0, lastSequence=0;
static uint32_t telemetryAt=0, imuAt=0, batteryAt=0, reconnectAt=0;
static sockaddr_in owner{};
static sockaddr_in finalOwner{};
static uint32_t finalSession=0, finalSequence=0;
static Status status{};
static Diagnostics diagnostics{};
static uint32_t loopAt=0;
static bool wasConnected=false;
static Frame pending{};
static Adafruit_NeoPixel matrixLeds(33,15,NEO_GRB+NEO_KHZ800), ringLeds(12,7,NEO_GRB+NEO_KHZ800);
static LedStatus ledStatus{};
static LedFrame pendingLeds{};
static uint32_t pendingFrameSequence=0, pendingLedSequence=0, ledTelemetryAt=0, lastLedSequence=0;
static bool ledsDirty=false;
static bool dirty=false, pcaOk=false, imuOk=false, imuConfigured=false, fault=false;

static bool writeReg(uint8_t address, uint8_t reg, uint8_t value) {
    Wire.beginTransmission(address); Wire.write(reg); Wire.write(value);
    return Wire.endTransmission()==0;
}
static bool readRegs(uint8_t address, uint8_t reg, uint8_t* out, size_t n) {
    Wire.beginTransmission(address); Wire.write(reg);
    if (Wire.endTransmission(false)!=0) return false;
    if (Wire.requestFrom(address, n, true)!=n) return false;
    for (size_t i=0;i<n;++i) out[i]=Wire.read();
    return true;
}
static bool writeServos(const uint16_t* ticks) {
    // AI=1, OCH=0: all sixteen channels latch on the same I2C STOP.
    uint8_t bytes[64];
    for (int i=0;i<16;++i) {
        bytes[4*i]=0; bytes[4*i+1]=0;
        bytes[4*i+2]=ticks[i]&255;
        bytes[4*i+3]=ticks[i] ? (ticks[i]>>8) : 0x10; // FULL_OFF
    }
    uint32_t start=micros();
    Wire.beginTransmission(PCA); Wire.write(0x06); Wire.write(bytes, sizeof bytes);
    bool ok=Wire.endTransmission()==0;
    status.apply_us=uint16_t(min(uint32_t(65535), uint32_t(micros()-start)));
    return ok;
}
static bool initPca() {
    // Disable all outputs before waking/configuring the oscillator.
    if (!writeReg(PCA,0xFD,0x10)) return false;
    if (!writeReg(PCA,0x00,0x30) || !writeReg(PCA,0x01,0x04) ||
        !writeReg(PCA,0xFE,PRESCALE) || !writeReg(PCA,0x00,0x20)) return false;
    delayMicroseconds(600);
    if (!writeReg(PCA,0x00,0xA0)) return false;
    if (!writeServos(status.ticks)) return false;
    // ALL_LED_* are broadcast writes to channel registers, not a separate gate.
    // Verify that every individual channel is FULL_OFF before accepting control.
    uint8_t registers[64];
    if (!readRegs(PCA,0x06,registers,sizeof registers)) return false;
    for(int i=0;i<16;++i) if(registers[4*i+3]!=0x10) return false;
    return true;
}
static bool initImu() {
    uint8_t who=0;
    if (!readRegs(IMU,0x0F,&who,1) || who!=0x6A) return false;
    // Block data update + auto-increment; 416 Hz, +/-4g and +/-500 dps.
    return writeReg(IMU,0x12,0x44) && writeReg(IMU,0x10,0x68) && writeReg(IMU,0x11,0x64);
}
static uint16_t flags() {
    bool on=false; for (auto t:status.ticks) if(t) on=true;
    return (session?OWNED:0) | (!session && on?HOLDING:0) | (pcaOk?PWM_OK:0) |
           (imuOk?IMU_OK:0) | (fault?FAULT:0) | (WiFi.isConnected()?WIFI_OK:0) | LED_READY | media_flags();
}
static void sendPacket(const sockaddr_in& dest, uint8_t type, uint32_t sid,
                       uint32_t seq, const void* payload, size_t size) {
    uint8_t out[192]; Header h=header(type,size,sid,seq);
    memcpy(out,&h,sizeof h); memcpy(out+sizeof h,payload,size);
    if(sendto(sock,out,sizeof h+size,MSG_DONTWAIT,(const sockaddr*)&dest,sizeof dest)<0) ++diagnostics.send_errors;
}
static void sendStatus(const sockaddr_in& dest, uint32_t sid, uint32_t seq) {
    status.uptime_us=micros(); status.flags=flags();
    status.buttons=(!digitalRead(4)?1:0)|(!digitalRead(38)?2:0);
    sendPacket(dest,cyo::STATUS,sid,seq,&status,sizeof status);
}
static void sendInfo(const sockaddr_in& dest, uint32_t seq) {
    Info info{}; memcpy(info.mac,mac,6); info.boot=bootId; info.challenge=challenge;
    info.flags=flags(); info.port=PORT; info.prescale=PRESCALE;
    info.minimum=MIN_TICK; info.maximum=MAX_TICK; info.lease_ms=LEASE_MS;
    sendPacket(dest,INFO,0,seq,&info,sizeof info);
}
static void sendLedStatus(const sockaddr_in& dest, uint32_t sid) {
    sendPacket(dest,LED_STATUS,sid,ledStatus.applied_seq,&ledStatus,sizeof ledStatus);
}
static void applyLeds(const LedFrame& f) {
    for(int i=0;i<33;++i) matrixLeds.setPixelColor(i,f.matrix[i][0],f.matrix[i][1],f.matrix[i][2]);
    for(int i=0;i<12;++i) ringLeds.setPixelColor(i,f.ring[i][0],f.ring[i][1],f.ring[i][2]);
    matrixLeds.show(); ringLeds.show();
}
static void releaseOwner(uint16_t reason) {
    // A fresh challenge prevents a delayed old CLAIM/FRAME from resuming motion.
    diagnostics.release_reason=reason;
    if(reason==1) ++diagnostics.lease_expirations;
    session=0; challenge=esp_random(); dirty=false; ledsDirty=false;
    media_owner(0,0);
    // Intentionally leave the PWM registers unchanged: hold last commanded pose.
}
static bool sameOwner(const sockaddr_in& source) {
    return source.sin_addr.s_addr==owner.sin_addr.s_addr && source.sin_port==owner.sin_port;
}
static void receivePacket(const uint8_t* bytes, size_t size, const sockaddr_in& source) {
    if (size<sizeof(Header)) { ++status.rejected; return; }
    Header h; memcpy(&h,bytes,sizeof h);
    if (memcmp(h.magic,"CYO2",4) || h.version!=1 || h.length!=size-sizeof h) {
        ++status.rejected; return;
    }
    const uint8_t* payload=bytes+sizeof h;
    if (h.type==DISCOVER && !h.length && !h.session) { sendInfo(source,h.seq); return; }
    if (h.type==DIAG_QUERY && !h.length && !h.session) {
        diagnostics.boot=bootId; diagnostics.uptime_ms=millis(); diagnostics.session=session;
        diagnostics.command_age_ms=uint32_t(millis()-lastCommand);
        diagnostics.received=status.received; diagnostics.rejected=status.rejected;
        diagnostics.rssi=WiFi.RSSI();
        sendPacket(source,DIAGNOSTICS,0,h.seq,&diagnostics,sizeof diagnostics); return;
    }
    // Idempotent OFF acknowledgement if its first response was lost.
    if (h.type==OFF && !h.length && !session && h.session==finalSession &&
        h.seq==finalSequence && source.sin_addr.s_addr==finalOwner.sin_addr.s_addr &&
        source.sin_port==finalOwner.sin_port) { sendStatus(source,h.session,h.seq); return; }
    if (h.type==CLAIM && h.length==sizeof(Claim) && h.session && !fault && pcaOk) {
        Claim c; memcpy(&c,payload,sizeof c);
        if (c.boot!=bootId || c.challenge!=challenge) { ++status.rejected; return; }
        if (!session) {
            finalSession=0;
            session=h.session; owner=source; lastSequence=h.seq; lastCommand=millis();
            media_owner(session,owner.sin_addr.s_addr);
            status.accepted_seq=h.seq; status.applied_seq=0;
            ledStatus.applied_seq=0;
            lastLedSequence=h.seq;
        }
        if (session==h.session && sameOwner(source)) { sendStatus(source,session,h.seq); sendLedStatus(source,session); }
        else ++status.rejected;
        return;
    }
    if (!session || h.session!=session || !sameOwner(source)) {
        ++status.rejected; return;
    }
    // LED and PWM packets can overtake each other over UDP. Each stream keeps
    // its own replay/order check, so a newer PWM frame cannot discard a LED edit.
    if (h.type==LED_FRAME) {
        if(h.length!=sizeof(LedFrame) || !newer(h.seq,lastLedSequence) || fault) { ++status.rejected; return; }
        memcpy(&pendingLeds,payload,sizeof pendingLeds); pendingLedSequence=lastLedSequence=h.seq; ledsDirty=true;
        lastCommand=millis(); ++status.received;
        return;
    }
    if (!newer(h.seq,lastSequence)) { ++status.rejected; return; }
    if (h.type==FRAME && h.length==sizeof(Frame) && !fault) {
        Frame f; memcpy(&f,payload,sizeof f);
        if (!validFrame(f)) { ++status.rejected; return; }
        pending=f; pendingFrameSequence=h.seq; dirty=true; // newest valid frame wins in this bounded receive batch
    } else if ((h.type==OFF || h.type==RELEASE) && !h.length) {
        if (h.type==OFF) {
            uint16_t off[16]={};
            if (writeServos(off)) memcpy(status.ticks,off,sizeof off);
            else { fault=true; pcaOk=false; }
            finalOwner=source; finalSession=h.session; finalSequence=h.seq;
        }
        status.accepted_seq=h.seq;
        releaseOwner(h.type==OFF?4:3); sendStatus(source,h.session,h.seq); return;
    } else { ++status.rejected; return; }
    lastSequence=h.seq; status.accepted_seq=h.seq;
    lastCommand=millis(); ++status.received;
}
void setup() {
    Serial.begin(115200);
    pinMode(4,INPUT); pinMode(38,INPUT);
    analogReadResolution(12); analogSetPinAttenuation(6,ADC_11db);
    Wire.setBufferSize(128); Wire.begin(17,18,400000); Wire.setTimeOut(5);
    // Power-up I2C may briefly be unavailable. Retry only at boot, with all
    // outputs off; a runtime hardware fault still requires explicit recovery.
    for(int attempt=0;attempt<3&&!pcaOk;++attempt){if(attempt)delay(20);pcaOk=initPca();}
    imuConfigured=imuOk=initImu(); fault=!pcaOk;
    matrixLeds.begin(); ringLeds.begin(); applyLeds(ledStatus.pixels);
    media_begin();
    bootId=esp_random(); challenge=esp_random();
    WiFi.mode(WIFI_STA); WiFi.setSleep(false); WiFi.setAutoReconnect(true);
    WiFi.macAddress(mac); WiFi.begin(WIFI_SSID,WIFI_PASSWORD);
    esp_task_wdt_add(nullptr);
    Serial.printf("CYO hardware bridge v1, UDP %u, PWM=%d IMU=%d, link loss=HOLD\n",PORT,pcaOk,imuOk);
}
void loop() {
    esp_task_wdt_reset();
    uint32_t now=millis();
    uint32_t loopNow=micros();
    if(loopAt) diagnostics.max_loop_us=max(diagnostics.max_loop_us,uint32_t(loopNow-loopAt));
    loopAt=loopNow;
    bool connected=WiFi.isConnected();
    if(wasConnected && !connected) ++diagnostics.wifi_losses;
    wasConnected=connected;
    if(session && !connected) releaseOwner(2);
    else if(session && uint32_t(now-lastCommand)>=LEASE_MS) releaseOwner(1);
    if (WiFi.isConnected()) {
        if(sock<0) {
            sock=socket(AF_INET,SOCK_DGRAM,IPPROTO_UDP);
            if(sock>=0) {
                sockaddr_in local{}; local.sin_family=AF_INET; local.sin_port=htons(PORT);
                if(bind(sock,(sockaddr*)&local,sizeof local)<0) { close(sock); sock=-1; }
                else { fcntl(sock,F_SETFL,O_NONBLOCK); Serial.printf("Ready: %s:%u\n",WiFi.localIP().toString().c_str(),PORT); }
            }
        }
        if(sock>=0) {
            // Bound draining to keep sensor sampling and lease checks responsive.
            for(int i=0;i<16;++i) {
                uint8_t buf[192]; sockaddr_in source{}; socklen_t n=sizeof source;
                int len=recvfrom(sock,buf,sizeof buf,MSG_DONTWAIT,(sockaddr*)&source,&n);
                if(len<0) break;
                receivePacket(buf,len,source);
            }
        }
    } else {
        if(sock>=0) { close(sock); sock=-1; }
        if(uint32_t(now-reconnectAt)>5000) { reconnectAt=now; WiFi.reconnect(); }
    }
    if(dirty && session) {
        dirty=false;
        if(writeServos(pending.ticks)) {
            memcpy(status.ticks,pending.ticks,sizeof status.ticks); status.applied_seq=pendingFrameSequence;
            ++status.applied;
        } else {
            // Latch a fault; partial I2C writes do not qualify as a successful command.
            fault=true; pcaOk=false; writeReg(PCA,0xFD,0x10); releaseOwner(5);
        }
    }
    if(ledsDirty && session) {
        ledsDirty=false;
        applyLeds(pendingLeds); ledStatus.pixels=pendingLeds; ledStatus.applied_seq=pendingLedSequence;
        sendLedStatus(owner,session); ledTelemetryAt=now;
    }
    if(uint32_t(now-imuAt)>=5) {
        imuAt=now; uint8_t sample[12];
        imuOk=imuConfigured && readRegs(IMU,0x22,sample,sizeof sample);
        if(imuOk) { memcpy(status.imu,sample,sizeof sample); status.imu_us=micros(); }
    }
    if(uint32_t(now-batteryAt)>=100) {
        batteryAt=now; status.battery_mv=uint16_t(min(uint32_t(65535),analogReadMilliVolts(6)*4));
    }
    if(session && sock>=0 && uint32_t(now-telemetryAt)>=10) {
        telemetryAt=now; sendStatus(owner,session,lastSequence);
    }
    if(session && sock>=0 && uint32_t(now-ledTelemetryAt)>=100) {
        ledTelemetryAt=now; sendLedStatus(owner,session);
    }
    delay(1);
}
