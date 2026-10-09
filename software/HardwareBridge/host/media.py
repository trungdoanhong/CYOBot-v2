"""microSD RPC and PCM duplex for the PC AI brain. Separate sockets from PWM."""
from collections import deque
from contextlib import contextmanager
import io
import json
import math
import select
import socket
import struct
import threading
import time
import sys

FILE_PORT, AUDIO_PORT = 4243, 4244
AUDIO_HEADER = struct.Struct('<BBHI')
SAMPLE_RATE, BLOCK_SAMPLES = 16000, 320
MAX_FILE = 32*1024*1024


def read_exact(stream, size):
    parts = bytearray()
    while len(parts) < size:
        chunk = stream.read(size-len(parts))
        if not chunk:
            raise ConnectionError('Robot closed the data connection')
        parts.extend(chunk)
    return bytes(parts)


def read_reply(stream):
    line = stream.readline(16385)
    if not line.endswith(b'\n') or len(line)>16384:
        raise ValueError('Invalid robot response')
    reply = json.loads(line)
    if not isinstance(reply,dict) or not reply.get('ok'):
        raise RuntimeError(reply.get('error','Robot is not responding') if isinstance(reply,dict) else 'Invalid response')
    return reply


def validate_path(path, root=False):
    if not isinstance(path,str) or not path.startswith('/') or len(path.encode('utf-8'))>220:
        raise ValueError('Invalid SD card path')
    if (not root and path=='/') or '\\' in path or '//' in path or any(ord(c)<32 for c in path):
        raise ValueError('Invalid SD card path')
    if any(part in ('.','..') for part in path.split('/')):
        raise ValueError('Invalid SD card path')
    return path


class RobotMedia:
    def __init__(self, robot):
        self.ip, self.session = robot.address[0], robot.session
        self.audio = None
        self._closed = threading.Event()
        self._audio_lock = threading.Lock()

    @contextmanager
    def request(self, op, **values):
        if self._closed.is_set():raise RuntimeError('Control session ended')
        with socket.create_connection((self.ip,FILE_PORT),timeout=3) as sock:
            sock.settimeout(5)
            sock.sendall((json.dumps(dict(op=op,session=self.session,**values),ensure_ascii=False)+'\n').encode())
            with sock.makefile('rb') as stream:
                reply=read_reply(stream)
                yield sock,stream,reply

    def info(self, mount=False):
        with self.request('mount' if mount else 'info') as (_,__,reply):return reply

    def files(self,path='/',offset=0):
        validate_path(path,root=True)
        if type(offset) is not int or not 0<=offset<=65535:raise ValueError('Invalid page')
        with self.request('list',path=path,offset=offset) as (_,__,reply):return reply

    def change(self,op,path,target=None):
        if op not in ('mkdir','rename','trash'):raise ValueError('Invalid SD operation')
        validate_path(path)
        values=dict(path=path)
        if op=='rename':values['target']=validate_path(target)
        with self.request(op,**values) as (_,__,reply):return reply

    def upload(self,path,source,size):
        validate_path(path)
        if type(size) is not int or not 0<=size<=MAX_FILE:raise ValueError('Files must be at most 32 MiB')
        with self.request('upload',path=path,size=size) as (sock,stream,_):
            remaining=size
            while remaining:
                if self._closed.is_set():raise RuntimeError('Control session ended')
                chunk=source.read(min(4096,remaining))
                if not chunk:raise ValueError('Upload is incomplete')
                sock.sendall(chunk);remaining-=len(chunk)
            return read_reply(stream)

    def download(self,path,destination):
        validate_path(path)
        with self.request('download',path=path) as (_,stream,reply):
            size=reply.get('size')
            if type(size) is not int or size<0:raise ValueError('Invalid file size')
            remaining=size
            while remaining:
                if self._closed.is_set():raise RuntimeError('Control session ended')
                data=read_exact(stream,min(4096,remaining));destination.write(data);remaining-=len(data)
            return size

    def start_audio(self):
        with self._audio_lock:
            if self._closed.is_set():raise RuntimeError('Control session ended')
            if self.audio and self.audio.alive:return self.audio
            if self.audio:self.audio.close()
            self.audio=AudioStream(self.ip,self.session)
            if self._closed.is_set():
                self.audio.close();raise RuntimeError('Control session ended')
            return self.audio

    def stop_audio(self):
        with self._audio_lock:
            if self.audio:self.audio.close()

    def close(self):
        self._closed.set()
        # Socket shutdown wakes the audio worker; never join inside PWM actor.
        if self.audio:self.audio.close()


class AudioStream:
    """16 kHz signed PCM16: read stereo mic, write mono speaker.

    Queues are bounded and expired speaker blocks are never replayed.
    Streaming never renews the robot's control lease. Keep Fleet/Studio running.
    """
    def __init__(self,ip,session):
        self.sock=socket.create_connection((ip,AUDIO_PORT),timeout=3)
        self.sock.setsockopt(socket.IPPROTO_TCP,socket.TCP_NODELAY,1)
        try:
            self.sock.sendall((json.dumps(dict(op='start',session=session))+'\n').encode())
            # Read exactly through the newline; do not buffer/drop first PCM bytes.
            response=bytearray()
            while not response.endswith(b'\n') and len(response)<1024:
                b=self.sock.recv(1)
                if not b:raise ConnectionError('Robot closed the audio stream')
                response.extend(b)
            reply=read_reply(io.BytesIO(response))
            if (reply.get('sample_rate'),reply.get('mic_channels'),reply.get('block_samples'))!=(16000,2,320):
                raise ValueError('Unsupported audio format')
        except BaseException:
            self.sock.close();raise
        self.sock.setblocking(False)
        self.stop=threading.Event();self.lock=threading.Lock();self.condition=threading.Condition(self.lock)
        self.mic=deque(maxlen=12);self.speaker=deque(maxlen=6);self.received=self.sent=self.dropped=0
        self.levels=[0,0];self.error='';self.volume=20;self._volume_pending=20
        self.last_mic_at=0;self.last_client_at=time.perf_counter()
        self.thread=threading.Thread(target=self._run,name='cyobot-pcm',daemon=True);self.thread.start()

    @property
    def alive(self):return not self.stop.is_set()

    def state(self):
        with self.lock:
            return dict(active=self.alive,received=self.received,sent=self.sent,dropped=self.dropped,
                levels=self.levels,volume=self.volume,error=self.error,
                mic_age_ms=round((time.perf_counter()-self.last_mic_at)*1000) if self.last_mic_at else None)

    def set_volume(self,value):
        if type(value) is not int or not 0<=value<=100:raise ValueError('Volume must be 0–100')
        with self.lock:self.volume=self._volume_pending=value

    def write_pcm(self,pcm):
        if not isinstance(pcm,bytes) or len(pcm)==0 or len(pcm)%640 or len(pcm)>640*6:
            raise ValueError('PCM mono 16 kHz: 320 samples / 640 bytes per block, at most 6 blocks')
        if not self.alive:raise RuntimeError(self.error or 'Audio stream stopped')
        now=time.perf_counter()
        with self.lock:
            for i in range(0,len(pcm),640):
                if len(self.speaker)==6:self.dropped+=1
                self.speaker.append((now,pcm[i:i+640]))
            self.last_client_at=now

    def clear_speaker(self):
        with self.lock:self.speaker.clear()

    def read_pcm(self,timeout=.1):
        with self.condition:
            if not self.mic and self.alive:self.condition.wait(timeout)
            self.last_client_at=time.perf_counter()
            # Discard old mic data after a paused AI/browser consumer.
            now=time.perf_counter()
            while self.mic and now-self.mic[0][0]>.25:self.mic.popleft();self.dropped+=1
            if not self.mic:return b''
            return self.mic.popleft()[1]

    def read_available(self,limit=3):
        parts=[]
        for _ in range(limit):
            data=self.read_pcm(timeout=.04 if not parts else 0)
            if not data:break
            parts.append(data)
        return b''.join(parts)

    def close(self):
        self.stop.set()
        try:self.sock.shutdown(socket.SHUT_RDWR)
        except OSError:pass
        self.sock.close()
        with self.condition:self.speaker.clear();self.mic.clear();self.condition.notify_all()

    def _run(self):
        buffer=bytearray();sequence=0;last_seq=None;out=b'';out_at=0;next_send=time.perf_counter()
        timer=None
        if sys.platform=='win32':
            # Windows otherwise rounds short waits to ~15.6 ms: 20 ms audio
            # pacing becomes ~31 ms. This request is process-scoped and balanced.
            try:
                import ctypes
                candidate=ctypes.WinDLL('winmm')
                if candidate.timeBeginPeriod(1)==0:timer=candidate
            except OSError:pass
        try:
            while not self.stop.is_set():
                now=time.perf_counter()
                if now-self.last_client_at>3:raise TimeoutError('No audio client · stream stopped')
                if out and now-out_at>.2:raise TimeoutError('Speaker backpressure · stream stopped')
                if not out and now>=next_send:
                    with self.lock:
                        volume,self._volume_pending=self._volume_pending,None
                        while self.speaker and now-self.speaker[0][0]>.2:self.speaker.popleft();self.dropped+=1
                        block=self.speaker.popleft()[1] if volume is None and self.speaker else None
                    if volume is not None or block:
                        sequence=(sequence+1)&0xffffffff
                        payload=bytes([volume]) if volume is not None else block
                        out=AUDIO_HEADER.pack(4 if volume is not None else 2,1,len(payload),sequence)+payload;out_at=now
                        if block:
                            next_send=now+.02 if now-next_send>.04 else next_send+.02
                            self.sent+=1
                readable,writable,_=select.select([self.sock],[self.sock] if out else [],[],.005)
                if writable:
                    count=self.sock.send(out);out=out[count:]
                if not readable:continue
                chunk=self.sock.recv(8192)
                if not chunk:raise ConnectionError('Robot stopped the audio stream')
                buffer.extend(chunk)
                while len(buffer)>=8:
                    kind,channels,size,seq=AUDIO_HEADER.unpack_from(buffer)
                    if kind!=1 or channels!=2 or size!=1280:raise ValueError('Invalid microphone PCM packet')
                    if len(buffer)<8+size:break
                    pcm=bytes(buffer[8:8+size]);del buffer[:8+size]
                    if last_seq is not None and not 0<((seq-last_seq)&0xffffffff)<0x80000000:continue
                    last_seq=seq
                    values=struct.unpack('<640h',pcm)
                    levels=[math.sqrt(sum(v*v for v in values[c::2])/320)/32768 for c in (0,1)]
                    with self.condition:
                        if len(self.mic)==12:self.dropped+=1
                        self.mic.append((time.perf_counter(),pcm));self.levels=levels;self.received+=1
                        self.last_mic_at=time.perf_counter();self.condition.notify_all()
        except (OSError,ValueError,TimeoutError) as exc:
            if not self.stop.is_set():self.error=str(exc)
        finally:
            if timer:timer.timeEndPeriod(1)
            self.stop.set()
            self.sock.close()
            with self.condition:self.condition.notify_all()
