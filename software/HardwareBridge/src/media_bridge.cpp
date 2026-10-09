// Separate tasks/sockets: FAT and PCM never block the UDP servo actor.
#include <Arduino.h>
#include <ArduinoJson.h>
#include <WiFi.h>
#include <SD.h>
#include <SPI.h>
#include <Wire.h>
#include <driver/i2s.h>
#include <lwip/sockets.h>
#include "media_bridge.h"
#include "protocol.h"
extern "C" {
#include "esp_codec_dev_defaults.h"
#include "es8311_codec.h"
#include "es7210_adc.h"
}

static portMUX_TYPE authMux=portMUX_INITIALIZER_UNLOCKED;
static uint32_t authSession=0, authIp=0;
static volatile bool sdReady=false, dacReady=false, adcReady=false, i2sReady=false;
static SPIClass cardSpi(FSPI);
static uint32_t micFrames=0, speakerFrames=0, underruns=0;
static const audio_codec_if_t *dac=nullptr, *adc=nullptr;

void media_owner(uint32_t sid,uint32_t ip) {
    portENTER_CRITICAL(&authMux); authSession=sid;authIp=ip;portEXIT_CRITICAL(&authMux);
}
static bool authorized(uint32_t sid,IPAddress ip) {
    portENTER_CRITICAL(&authMux);
    bool ok=sid && sid==authSession && uint32_t(ip)==authIp;
    portEXIT_CRITICAL(&authMux);return ok;
}
uint16_t media_flags() {
    return cyo::MEDIA_READY | (sdReady?cyo::SD_READY:0) | (i2sReady&&dacReady&&adcReady?cyo::AUDIO_READY:0);
}
struct CodecCtrl { audio_codec_ctrl_if_t base; uint8_t address; };
static bool ctrlOpen(const audio_codec_ctrl_if_t*) {return true;}
static int ctrlInit(const audio_codec_ctrl_if_t*,void*,int) {return 0;}
static int ctrlClose(const audio_codec_ctrl_if_t*) {return 0;}
static int ctrlWrite(const audio_codec_ctrl_if_t* h,int reg,int regLen,void* data,int len) {
    if(regLen!=1||len<0||len>64)return -1;
    Wire.beginTransmission(((const CodecCtrl*)h)->address);Wire.write(reg);Wire.write((uint8_t*)data,len);
    return Wire.endTransmission()==0?0:-1;
}
static int ctrlRead(const audio_codec_ctrl_if_t* h,int reg,int regLen,void* data,int len) {
    if(regLen!=1||len<=0||len>64)return -1;
    uint8_t addr=((const CodecCtrl*)h)->address;
    Wire.beginTransmission(addr);Wire.write(reg);
    if(Wire.endTransmission(false)||Wire.requestFrom(addr,size_t(len),true)!=len)return -1;
    for(int i=0;i<len;++i)((uint8_t*)data)[i]=Wire.read();return 0;
}
static CodecCtrl dacCtrl{},adcCtrl{};
static void makeCtrl(CodecCtrl& c,uint8_t addr) {
    c.address=addr;c.base={ctrlInit,ctrlOpen,ctrlRead,ctrlWrite,ctrlClose};
}
static bool probe(uint8_t addr) {Wire.beginTransmission(addr);return Wire.endTransmission()==0;}
static bool initAudio() {
    pinMode(47,OUTPUT);digitalWrite(47,LOW); // GPIO, not the module's physical pin 25
    i2s_config_t cfg{};
    cfg.mode=i2s_mode_t(I2S_MODE_MASTER|I2S_MODE_TX|I2S_MODE_RX);
    cfg.sample_rate=16000;cfg.bits_per_sample=I2S_BITS_PER_SAMPLE_16BIT;
    cfg.channel_format=I2S_CHANNEL_FMT_RIGHT_LEFT;cfg.communication_format=I2S_COMM_FORMAT_STAND_I2S;
    cfg.intr_alloc_flags=ESP_INTR_FLAG_LEVEL1;cfg.dma_buf_count=6;cfg.dma_buf_len=320;
    cfg.use_apll=false;cfg.tx_desc_auto_clear=true;cfg.fixed_mclk=4096000;
    cfg.mclk_multiple=I2S_MCLK_MULTIPLE_256;
    if(i2s_driver_install(I2S_NUM_0,&cfg,0,nullptr)!=ESP_OK)return false;
    i2s_pin_config_t pins{};pins.mck_io_num=16;pins.bck_io_num=9;pins.ws_io_num=45;
    pins.data_out_num=8;pins.data_in_num=10;
    if(i2s_set_pin(I2S_NUM_0,&pins)!=ESP_OK)return false;
    i2sReady=true;i2s_zero_dma_buffer(I2S_NUM_0);
    esp_codec_dev_sample_info_t fs{};fs.bits_per_sample=16;fs.channel=2;fs.sample_rate=16000;fs.mclk_multiple=256;
    uint8_t dacAddr=probe(0x18)?0x18:0x19;
    if(probe(dacAddr)) {
        makeCtrl(dacCtrl,dacAddr);
        es8311_codec_cfg_t c{};c.ctrl_if=&dacCtrl.base;c.codec_mode=ESP_CODEC_DEV_WORK_MODE_DAC;
        c.pa_pin=-1;c.use_mclk=true;c.mclk_div=256;c.no_dac_ref=true;
        dac=es8311_codec_new(&c);
        dacReady=dac && !dac->set_fs(dac,&fs) && !dac->enable(dac,true) && !dac->set_vol(dac,-6);
    }
    if(probe(0x40)) {
        makeCtrl(adcCtrl,0x40);es7210_codec_cfg_t c{};c.ctrl_if=&adcCtrl.base;
        c.mic_selected=ES7120_SEL_MIC1|ES7120_SEL_MIC2;c.mclk_div=256;
        adc=es7210_codec_new(&c);
        // enable() restores the driver's default gain; apply mic gain afterwards.
        adcReady=adc && !adc->set_fs(adc,&fs) && !adc->enable(adc,true) && !adc->set_mic_gain(adc,24);
    }
    digitalWrite(47,LOW);
    Serial.printf("Media audio: I2S=%d ES8311=%d (0x%02x) ES7210=%d\n",i2sReady,dacReady,dacAddr,adcReady);
    return dacReady&&adcReady;
}
static void reply(WiFiClient& c,JsonDocument& d) {serializeJson(d,c);c.print('\n');}
static void error(WiFiClient& c,const char* message) {
    StaticJsonDocument<256> d;d["ok"]=false;d["error"]=message;reply(c,d);
}
static bool request(WiFiClient& c,JsonDocument& doc) {
    c.setTimeout(2500);char line[1025];size_t size=c.readBytesUntil('\n',line,1024);line[size]=0;
    // Copy strings into the document: this stack buffer expires on return.
    if(size>=1024||deserializeJson(doc,static_cast<const char*>(line))) {error(c,"Invalid media request");return false;}
    if(!authorized(doc["session"]|uint32_t(0),c.remoteIP())) {error(c,"Control session expired");return false;}
    return true;
}
static bool validPath(const String& p,bool root=false) {
    if(p.length()==0||p.length()>220||p[0]!='/'||(!root&&p=="/"))return false;
    if(p.indexOf("//")>=0||p.indexOf('\\')>=0)return false;
    for(unsigned i=0;i<p.length();++i)if(uint8_t(p[i])<32)return false;
    int at=1;
    while(at<int(p.length())) {int end=p.indexOf('/',at);if(end<0)end=p.length();
        String part=p.substring(at,end);if(part=="."||part=="..")return false;at=end+1;}
    return true;
}
static bool writeAll(WiFiClient& c,const uint8_t* p,size_t n,uint32_t sid) {
    uint32_t at=millis();
    while(n&&c.connected()&&authorized(sid,c.remoteIP())) {
        size_t sent=c.write(p,n);if(!sent){if(millis()-at>2500)return false;vTaskDelay(1);continue;}
        p+=sent;n-=sent;at=millis();
    }return !n;
}
static void handleFile(WiFiClient& c) {
    StaticJsonDocument<1536> req;if(!request(c,req))return;
    String op=req["op"]|"";uint32_t sid=req["session"]|uint32_t(0);
    DynamicJsonDocument out(12000);out["ok"]=true;
    if(op=="info"||op=="mount") {
        if(op=="mount") {SD.end();sdReady=SD.begin(14,cardSpi,4000000,"/sd",5,false);}
        out["sd_ready"]=sdReady;out["dac_ready"]=dacReady;out["adc_ready"]=adcReady;
        out["audio_ready"]=i2sReady&&dacReady&&adcReady;out["sample_rate"]=16000;
        out["mic_channels"]=2;out["speaker_channels"]=1;
        out["mic_frames"]=micFrames;out["speaker_frames"]=speakerFrames;out["underruns"]=underruns;
        if(sdReady){out["total"]=SD.totalBytes();out["used"]=SD.usedBytes();}
        reply(c,out);return;
    }
    if(!sdReady){error(c,"No readable microSD card; insert FAT32 card and reconnect card");return;}
    String path=req["path"]|"";if(!validPath(path,op=="list")){error(c,"Invalid path");return;}
    if(op=="list") {
        File dir=SD.open(path);if(!dir||!dir.isDirectory()){error(c,"Folder not found");return;}
        uint32_t offset=req["offset"]|uint32_t(0),index=0,count=0;
        JsonArray entries=out.createNestedArray("entries");File f;
        while((f=dir.openNextFile())) {
            if(index++<offset){f.close();continue;}
            String name=f.name();
            if(count++==64||out.capacity()-out.memoryUsage()<name.length()+256){out["next"]=index-1;f.close();break;}
            JsonObject item=entries.createNestedObject();item["name"]=name;item["directory"]=f.isDirectory();item["size"]=f.size();f.close();
        }
        dir.close();out["path"]=path;reply(c,out);return;
    }
    if(op=="download") {
        File f=SD.open(path,FILE_READ);if(!f||f.isDirectory()){error(c,"File not found");return;}
        out["size"]=f.size();reply(c,out);uint8_t buf[4096];
        while(f.available()&&c.connected()&&authorized(sid,c.remoteIP())) {int n=f.read(buf,sizeof buf);if(n<=0||!writeAll(c,buf,n,sid))break;}
        f.close();return;
    }
    if(op=="upload") {
        uint32_t size=req["size"]|uint32_t(0);if(size>32UL*1024*1024||SD.exists(path)){error(c,"File exists or exceeds 32 MiB");return;}
        String staging;
        for(int i=0;i<8;++i){staging="/.cyobot-upload-"+String(esp_random(),HEX);if(!SD.exists(staging))break;}
        if(SD.exists(staging)){error(c,"Cannot allocate upload file");return;}
        File f=SD.open(staging,FILE_WRITE);
        if(!f){error(c,"Cannot create upload");return;}reply(c,out);
        uint8_t buf[4096];uint32_t remaining=size;bool ok=true;
        while(remaining&&c.connected()&&authorized(sid,c.remoteIP())) {
            size_t n=c.readBytes(buf,min(uint32_t(sizeof buf),remaining));
            if(!n||f.write(buf,n)!=n){ok=false;break;}remaining-=n;
        }
        f.flush();f.close();
        if(!remaining&&ok&&authorized(sid,c.remoteIP())&&!SD.exists(path)&&SD.rename(staging,path)){out["size"]=size;reply(c,out);}
        else {SD.remove(staging);error(c,"Upload interrupted; target unchanged");}return;
    }
    bool ok=false;
    if(op=="mkdir")ok=!SD.exists(path)&&SD.mkdir(path);
    else if(op=="rename") {
        String target=req["target"]|"";ok=validPath(target)&&!SD.exists(target)&&SD.rename(path,target);
    } else if(op=="trash") {
        if(path=="/.cyobot-trash"||path.startsWith("/.cyobot-trash/")){error(c,"Use rename to restore items from trash");return;}
        if(!SD.exists("/.cyobot-trash"))SD.mkdir("/.cyobot-trash");
        String target="/.cyobot-trash/"+String(esp_random(),HEX)+"-"+path.substring(path.lastIndexOf('/')+1);
        ok=SD.rename(path,target);out["target"]=target;
    } else {error(c,"Unknown file operation");return;}
    if(!ok){error(c,"Operation failed; check path and card");return;}reply(c,out);
}
static void fileTask(void*) {
    while(!WiFi.isConnected())vTaskDelay(pdMS_TO_TICKS(100));WiFiServer server(4243);server.begin();
    while(true){WiFiClient c=server.available();if(c){c.setNoDelay(true);handleFile(c);c.stop();}vTaskDelay(1);}
}
#pragma pack(push,1)
struct AudioHeader {uint8_t type,channels;uint16_t bytes;uint32_t seq;};
#pragma pack(pop)
static_assert(sizeof(AudioHeader)==8,"PCM header");
static void audioTask(void*) {
    while(!WiFi.isConnected())vTaskDelay(pdMS_TO_TICKS(100));WiFiServer server(4244);server.begin();
    WiFiClient client;uint32_t sid=0,seq=0,lastPcm=0,lastSeq=0;int volume=20;
    static uint8_t incoming[4096];size_t fill=0;
    static int16_t mic[640],mono[320],stereo[640];
    static int16_t playback[6][320];unsigned playHead=0,playCount=0;
    static uint8_t outgoing[1288];size_t outSize=0,outOffset=0;uint32_t outAt=0;
    while(true) {
        if(sid && (!client.connected()||!authorized(sid,client.remoteIP()))) {client.stop();fill=0;playCount=0;outSize=outOffset=0;sid=0;digitalWrite(47,LOW);}
        WiFiClient candidate=server.available();
        if(candidate) {
            if(client.connected()){error(candidate,"Audio stream busy");candidate.stop();}
            else {
                StaticJsonDocument<512> req;
                if(request(candidate,req)&&req["op"]=="start"&&i2sReady&&dacReady&&adcReady) {
                    client=candidate;client.setNoDelay(true);sid=req["session"];seq=lastSeq=0;fill=0;playCount=0;outSize=outOffset=0;lastPcm=0;volume=20;
                    StaticJsonDocument<256> out;out["ok"]=true;out["sample_rate"]=16000;out["mic_channels"]=2;
                    out["speaker_channels"]=1;out["block_samples"]=320;out["format"]="s16le";reply(client,out);
                } else {error(candidate,"Audio hardware unavailable");candidate.stop();}
            }
        }
        bool havePcm=false;memset(mono,0,sizeof mono);
        if(client.connected()) {
            // Jitter buffer capped at 120 ms; discard oldest if the sender floods.
            int n=client.available();if(n>0&&fill<sizeof incoming){int got=client.read(incoming+fill,min(size_t(n),sizeof incoming-fill));if(got>0)fill+=got;}
            while(fill>=sizeof(AudioHeader)) {
                AudioHeader h;memcpy(&h,incoming,sizeof h);
                if((h.type!=2&&h.type!=4)||h.bytes>640||(h.type==2&&(h.bytes!=640||h.channels!=1))||(h.type==4&&h.bytes!=1)){client.stop();fill=0;break;}
                size_t total=sizeof h+h.bytes;if(fill<total)break;
                if(cyo::newer(h.seq,lastSeq)){lastSeq=h.seq;
                    if(h.type==2){
                        if(playCount==6){playHead=(playHead+1)%6;--playCount;}
                        memcpy(playback[(playHead+playCount)%6],incoming+sizeof h,640);++playCount;
                    }
                    else volume=min(100,int(incoming[sizeof h]));}
                memmove(incoming,incoming+total,fill-total);fill-=total;
            }
        }
        if(playCount&&client.connected()) {
            memcpy(mono,playback[playHead],640);playHead=(playHead+1)%6;--playCount;
            havePcm=true;lastPcm=millis();++speakerFrames;
        }
        for(int i=0;i<320;++i)stereo[2*i]=stereo[2*i+1]=int32_t(mono[i])*volume/100;
        bool amp=client.connected()&&lastPcm&&uint32_t(millis()-lastPcm)<200&&volume>0;
        digitalWrite(47,amp?HIGH:LOW);
        size_t written=0,read=0;
        if(i2sReady) {
            i2s_write(I2S_NUM_0,stereo,sizeof stereo,&written,pdMS_TO_TICKS(30));
            i2s_read(I2S_NUM_0,mic,sizeof mic,&read,pdMS_TO_TICKS(30));
            if(client.connected()&&read==sizeof mic) {
                // Finish partial TCP writes without blocking PWM or breaking framing.
                // Keep at most one frame; discard new captures during congestion.
                if(!outSize){AudioHeader h{1,2,uint16_t(read),++seq};memcpy(outgoing,&h,8);memcpy(outgoing+8,mic,read);
                    outSize=read+8;outOffset=0;outAt=millis();}
                int sent=send(client.fd(),outgoing+outOffset,outSize-outOffset,MSG_DONTWAIT);
                if(sent>0){outOffset+=sent;if(outOffset==outSize){outSize=outOffset=0;++micFrames;}}
                else if(sent==0||(sent<0&&errno!=EAGAIN&&errno!=EWOULDBLOCK)){client.stop();}
                if(outSize&&uint32_t(millis()-outAt)>250)client.stop();
            }
            if(client.connected()&&!havePcm)++underruns;
        } else vTaskDelay(pdMS_TO_TICKS(20));
    }
}
void media_begin() {
    cardSpi.begin(12,13,11,14);
    sdReady=SD.begin(14,cardSpi,4000000,"/sd",5,false);
    Serial.printf("Media microSD: %d (never auto-format)\n",sdReady);
    initAudio();
    xTaskCreatePinnedToCore(fileTask,"cyo-files",16384,nullptr,1,nullptr,0);
    xTaskCreatePinnedToCore(audioTask,"cyo-audio",12288,nullptr,1,nullptr,0);
}
