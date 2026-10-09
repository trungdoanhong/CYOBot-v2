"""Transport tests use loopback sockets and in-memory cards, never the robot."""
import http.client
import io
import json
from pathlib import Path
import re
import socket
import struct
import sys
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'host'))
import media
from studio import create_server

class Fragmented(io.BytesIO):
    def read(self,n=-1):return super().read(min(3,n) if n>=0 else 3)

class CardServer:
    def __init__(self):
        self.sock=socket.socket();self.sock.bind(('127.0.0.1',0));self.sock.listen();self.sock.settimeout(.05)
        self.port=self.sock.getsockname()[1];self.stop=threading.Event();self.files={'/hello.bin':b'original'};self.dirs={'/'};self.ops=[];self.errors=[]
        self.thread=threading.Thread(target=self.run,daemon=True);self.thread.start()
    def run(self):
        while not self.stop.is_set():
            try:c,_=self.sock.accept()
            except socket.timeout:continue
            except OSError:break
            with c:
                try:
                    c.settimeout(1)
                    with c.makefile('rb') as stream:
                        r=json.loads(stream.readline());self.ops.append(r);op=r['op'];path=r.get('path')
                        def reply(**v):c.sendall((json.dumps(v)+'\n').encode())
                        if r['session']!=123:reply(ok=False,error='expired');continue
                        if op in ('info','mount'):reply(ok=True,sd_ready=True,audio_ready=True,total=1048576,used=sum(map(len,self.files.values())))
                        elif op=='list':
                            prefix=path.rstrip('/')+'/'
                            entries=[dict(name=p[len(prefix):],directory=False,size=len(v)) for p,v in self.files.items() if p.startswith(prefix) and '/' not in p[len(prefix):]]
                            entries.extend(dict(name=p[len(prefix):],directory=True,size=0) for p in self.dirs if p!=path and p.startswith(prefix) and '/' not in p[len(prefix):])
                            reply(ok=True,entries=entries,next=None)
                        elif op=='download':
                            data=self.files[path];reply(ok=True,size=len(data))
                            for at in range(0,len(data),7):c.sendall(data[at:at+7])
                        elif op=='upload':
                            if path in self.files:reply(ok=False,error='File already exists');continue
                            reply(ok=True);data=media.read_exact(stream,r['size']);self.files[path]=data;reply(ok=True,size=len(data))
                        elif op=='mkdir':self.dirs.add(path);reply(ok=True)
                        elif op=='rename':self.files[r['target']]=self.files.pop(path);reply(ok=True)
                        elif op=='trash':
                            self.dirs.add('/.cyobot-trash');self.files['/.cyobot-trash/test-'+path.split('/')[-1]]=self.files.pop(path);reply(ok=True,target='/.cyobot-trash/test-'+path.split('/')[-1])
                except (OSError,ConnectionError):pass
                except Exception as e:self.errors.append(repr(e))
    def close(self):self.stop.set();self.sock.close();self.thread.join(1)

class MediaTests(unittest.TestCase):
    def test_paths_block_traversal_control_bytes_and_utf8_overflow(self):
        for p in ['../a','/../a','/x/./a','/a//b','/a\\b','/a\x00','/','/'+'ệ'*74]:
            with self.assertRaises(ValueError):media.validate_path(p)
        self.assertEqual(media.validate_path('/âm thanh/test.wav'),'/âm thanh/test.wav')
        self.assertEqual(media.validate_path('/',root=True),'/')
    def test_exact_read_fragmentation_and_premature_eof(self):
        self.assertEqual(media.read_exact(Fragmented(b'0123456789'),10),b'0123456789')
        with self.assertRaises(ConnectionError):media.read_exact(Fragmented(b'123'),4)
    def test_reply_size_framing_and_failure(self):
        for b in [b'{}',b'[]\n',b'{"ok":true}'+b' '*17000+b'\n']:
            with self.assertRaises((ValueError,RuntimeError)):media.read_reply(io.BytesIO(b))
        with self.assertRaisesRegex(RuntimeError,'missing'):media.read_reply(io.BytesIO(b'{"ok":false,"error":"missing"}\n'))
    def setUp(self):
        self.card=CardServer();self.patcher=patch.object(media,'FILE_PORT',self.card.port);self.patcher.start()
        self.media=media.RobotMedia(SimpleNamespace(address=('127.0.0.1',4242),session=123))
    def tearDown(self):self.media.close();self.patcher.stop();self.card.close();self.assertFalse(self.card.errors)
    def test_card_roundtrip_binary_upload_download_and_list(self):
        data=bytes(range(256))*41
        self.assertTrue(self.media.info()['sd_ready']);self.assertEqual(self.media.upload('/data.bin',Fragmented(data),len(data))['size'],len(data))
        target=io.BytesIO();self.assertEqual(self.media.download('/data.bin',target),len(data));self.assertEqual(target.getvalue(),data)
        self.assertIn('data.bin',[f['name'] for f in self.media.files()['entries']])
    def test_existing_file_preserved_and_short_upload_not_published(self):
        with self.assertRaisesRegex(RuntimeError,'exists'):self.media.upload('/hello.bin',io.BytesIO(b'changed'),7)
        self.assertEqual(self.card.files['/hello.bin'],b'original')
        with self.assertRaises(ValueError):self.media.upload('/broken.bin',io.BytesIO(b'12'),20)
        time.sleep(.03);self.assertNotIn('/broken.bin',self.card.files)
    def test_rename_trash_and_restore(self):
        self.media.change('mkdir','/voice');self.assertIn('/voice',self.card.dirs)
        self.media.change('rename','/hello.bin','/renamed.bin')
        result=self.media.change('trash','/renamed.bin');self.assertNotIn('/renamed.bin',self.card.files)
        self.media.change('rename',result['target'],'/restored.bin');self.assertEqual(self.card.files['/restored.bin'],b'original')
    def test_expired_and_closed_sessions_cannot_mutate_card(self):
        self.media.session=999
        with self.assertRaisesRegex(RuntimeError,'expired'):self.media.change('mkdir','/bad')
        self.assertNotIn('/bad',self.card.dirs);self.media.close()
        with self.assertRaises(RuntimeError):self.media.info()
    def test_http_owner_token_and_session_boundaries(self):
        fake=SimpleNamespace(media=self.media,state=lambda:dict(connected=True,owner='window',media_supported=True))
        server=create_server(fake,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        c=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
        try:
            c.request('GET','/');r=c.getresponse();token=re.search('name="cyo-token" content="([^"]+)"',r.read().decode())[1]
            h={'X-CYO-Token':token,'X-CYO-Client':'window','X-CYO-Session':'123'}
            for headers in [{},{**h,'X-CYO-Client':'other'},{**h,'X-CYO-Session':'122'}]:
                c.request('GET','/api/media/info',headers=headers);r=c.getresponse();r.read();self.assertEqual(r.status,409)
            self.assertEqual(self.card.ops,[])
            c.request('GET','/api/media/info',headers=h);r=c.getresponse();self.assertTrue(json.loads(r.read())['sd_ready']);self.assertEqual(r.status,200)
            data=b'PCM or arbitrary file\0\xff';c.request('POST','/api/media/upload?path=/new.bin',data,h);r=c.getresponse();r.read();self.assertEqual(r.status,200)
            c.request('GET','/api/media/download?path=/new.bin',headers=h);r=c.getresponse();self.assertEqual(r.read(),data)
        finally:c.close();server.shutdown();server.server_close();thread.join(1)

class AudioTests(unittest.TestCase):
    def test_fragmented_duplex_pcm_and_socket_shutdown(self):
        server=socket.socket();server.bind(('127.0.0.1',0));server.listen();received=[];errors=[];end=threading.Event()
        pcm=struct.pack('<640h',*([1000,-2000]*320))
        def robot():
            try:
                c,_=server.accept()
                with c,c.makefile('rb') as stream:
                    r=json.loads(stream.readline());assert r['session']==123
                    # First PCM immediately follows handshake, exposing buffered-read bugs.
                    handshake=b'{"ok":true,"sample_rate":16000,"mic_channels":2,"speaker_channels":1,"block_samples":320}\n'
                    frame=media.AUDIO_HEADER.pack(1,2,1280,1)+pcm
                    c.sendall(handshake+frame[:19]);c.sendall(frame[19:])
                    while not end.is_set():
                        header=media.read_exact(stream,8);kind,ch,size,seq=media.AUDIO_HEADER.unpack(header)
                        received.append((kind,seq,media.read_exact(stream,size)))
            except (OSError,ConnectionError):pass
            except Exception as e:errors.append(repr(e))
        t=threading.Thread(target=robot,daemon=True);t.start()
        with patch.object(media,'AUDIO_PORT',server.getsockname()[1]):audio=media.AudioStream('127.0.0.1',123)
        try:
            self.assertEqual(audio.read_pcm(.5),pcm);self.assertAlmostEqual(audio.state()['levels'][0],1000/32768)
            with self.assertRaises(ValueError):audio.write_pcm(b'bad')
            audio.set_volume(7);audio.write_pcm(bytes(640));deadline=time.perf_counter()+.6
            while not any(r[0]==2 for r in received) and time.perf_counter()<deadline:time.sleep(.005)
            self.assertTrue(any(r[0]==4 and r[2]==b'\x07' for r in received));self.assertTrue(any(r[0]==2 and r[2]==bytes(640) for r in received))
            self.assertEqual([r[1] for r in received],sorted({r[1] for r in received}))
        finally:audio.close();end.set();server.close();t.join(1);audio.thread.join(1)
        self.assertFalse(audio.alive);self.assertFalse(audio.thread.is_alive());self.assertFalse(errors)
    def test_bounded_queue_discards_expired_pcm(self):
        # Isolate queue semantics; no socket thread races or wall-clock sleeps.
        audio=media.AudioStream.__new__(media.AudioStream);audio.stop=threading.Event();audio.lock=threading.Lock()
        audio.condition=threading.Condition(audio.lock);audio.speaker=media.deque(maxlen=6);audio.mic=media.deque(maxlen=12);audio.dropped=0;audio.error=''
        for _ in range(8):audio.write_pcm(bytes(640))
        self.assertEqual(len(audio.speaker),6);self.assertEqual(audio.dropped,2)
        audio.mic.extend([(time.perf_counter()-1,b'old'),(time.perf_counter(),b'new')])
        self.assertEqual(audio.read_pcm(0),b'new');self.assertEqual(audio.dropped,3)
        audio.clear_speaker();self.assertEqual(len(audio.speaker),0)

if __name__=='__main__':unittest.main()
