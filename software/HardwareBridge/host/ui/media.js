const $=s=>document.querySelector(s);
const delay=ms=>new Promise(r=>setTimeout(r,ms));
const bytes=n=>n>=1048576?(n/1048576).toFixed(1)+' MB':n>=1024?(n/1024).toFixed(1)+' KB':n+' B';
export function createMediaPanel({getState,client,token,toast}) {
  let session=null,info=null,path='/',offset=0,next=null,filesBusy=false;
  let running=false,starting=false,listening=false,talking=false,playing=false,talkPending=false,epoch=0,startedAt=0;
  let ctx=null,node=null,mic=null,source=null,abort=null,speakerQueue=[],sending=false,fileEpoch=0;
  const usable=()=>{const s=getState();return s.connected&&s.owner===client&&s.media_supported;};
  const headers=()=>({'X-CYO-Token':token,'X-CYO-Client':client,'X-CYO-Session':String(getState().control_session)});
  async function request(url,options={}) {
    const r=await fetch(url,{...options,headers:{...headers(),...options.headers}});
    if(!r.ok){const e=await r.json().catch(()=>({}));throw Error(e.error||'Robot is not responding');}return r;
  }
  async function action(op,values={}) {return (await request('/api/media/action',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({op,...values,client,control_session:getState().control_session})})).json();}
  function message(error){toast(error.message||String(error),true);}
  function audioLabels() {
    $('#audio-listen').classList.toggle('active',listening);$('#audio-listen').setAttribute('aria-pressed',String(listening));
    $('#audio-talk').classList.toggle('active',talking);$('#audio-talk').setAttribute('aria-pressed',String(talking));
    $('#audio-live').textContent=starting?'Opening…':running?'LIVE · 16 kHz':'Ready';
    $('#audio-live').classList.toggle('live',running);$('#audio-stop').disabled=!running&&!starting;
    $('#audio-source').textContent=talking?'PC microphone → robot speaker':playing?'PC file → robot speaker':running&&listening?'Robot microphones → PC':running?'Stream is open':'Choose an audio source';
  }
  async function context() {
    if(!ctx){ctx=new AudioContext();await ctx.audioWorklet.addModule('/audio-worklet.js');
      node=new AudioWorkletNode(ctx,'cyobot-duplex',{numberOfInputs:1,numberOfOutputs:1,outputChannelCount:[2]});
      node.connect(ctx.destination);node.port.onmessage=({data})=>{if(data.pcm&&talking&&running)queueSpeaker(data.pcm);};}
    await ctx.resume();
  }
  function endTalk(){talking=false;node?.port.postMessage({capture:false});source?.disconnect();source=null;mic?.getTracks().forEach(t=>t.stop());mic=null;}
  function localStop(){epoch++;fileEpoch++;running=false;starting=false;listening=false;playing=false;endTalk();
    node?.port.postMessage({listen:false});speakerQueue=[];abort?.abort();abort=null;$('#audio-file-name').textContent='Audio from your computer';audioLabels();}
  async function stop(){localStop();if(usable())try{await action('audio_stop');}catch(e){message(e);}}
  async function start() {
    if(!usable())throw Error('Connect a robot first');if(running)return;if(starting)throw Error('Stream is open');
    starting=true;audioLabels();const ticket=epoch;
    try{await context();await action('audio_start');
      if(ticket!==epoch){if(usable())await action('audio_stop');return;}
      await action('volume',{value:+$('#audio-volume').value});running=true;startedAt=performance.now();abort=new AbortController();
      micLoop(epoch,abort.signal);
    }finally{starting=false;audioLabels();}
  }
  async function micLoop(ticket,signal) {
    while(running&&ticket===epoch){const at=performance.now();
      try{const r=await request('/api/media/mic',{signal});const pcm=await r.arrayBuffer();
        if(ticket!==epoch)return;if(listening&&pcm.byteLength)node.port.postMessage({pcm},[pcm]);
      }catch(e){if(ticket===epoch){localStop();message(e);}return;}
      await delay(Math.max(0,40-(performance.now()-at)));
    }
  }
  function queueSpeaker(pcm){speakerQueue.push({pcm,at:performance.now(),ticket:epoch});if(speakerQueue.length>6)speakerQueue.shift();sendSpeaker();}
  async function sendSpeaker(){if(sending)return;sending=true;
    try{while(running&&speakerQueue.length){const block=speakerQueue.shift();if(block.ticket!==epoch||performance.now()-block.at>200)continue;
      await request('/api/media/pcm',{method:'POST',body:block.pcm,signal:abort?.signal});}}
    catch(e){if(running){localStop();message(e);}}finally{sending=false;}
  }
  $('#audio-listen').onclick=async()=>{try{await start();if(!running)return;listening=!listening;node.port.postMessage({listen:listening});audioLabels();
    if(!listening&&!talking&&!playing)await stop();}catch(e){message(e);}};
  $('#audio-talk').onclick=async()=>{if(talkPending)return;talkPending=true;try{if(talking){endTalk();audioLabels();if(!listening)await stop();return;}
    await start();if(!running)return;const ticket=epoch;fileEpoch++;playing=false;
    const stream=await navigator.mediaDevices.getUserMedia({audio:{echoCancellation:true,noiseSuppression:true},video:false});
    if(ticket!==epoch){stream.getTracks().forEach(t=>t.stop());return;}
    mic=stream;source=ctx.createMediaStreamSource(mic);source.connect(node);talking=true;node.port.postMessage({capture:true});audioLabels();
  }catch(e){message(e.name==='NotAllowedError'?Error('Allow microphone access to talk through the robot'):e);if(!listening)await stop();}finally{talkPending=false;}};
  $('#audio-stop').onclick=stop;
  let volumeTimer;$('#audio-volume').oninput=()=>{$('#audio-volume-value').textContent=$('#audio-volume').value+'%';clearTimeout(volumeTimer);
    volumeTimer=setTimeout(()=>{if(running)action('volume',{value:+$('#audio-volume').value}).catch(message);},80);};
  $('#audio-file').onchange=async e=>{const file=e.target.files[0];e.target.value='';if(!file)return;
    let ticket;
    try{if(file.size>32*1048576)throw Error('Audio files must be at most 32 MB');await start();if(!running)return;endTalk();
      ticket=++fileEpoch;const control=epoch;playing=true;$('#audio-file-name').textContent=file.name;audioLabels();
      const decoded=await ctx.decodeAudioData(await file.arrayBuffer());const channels=Array.from({length:decoded.numberOfChannels},(_,i)=>decoded.getChannelData(i));
      const count=Math.floor(decoded.duration*16000),ratio=decoded.sampleRate/16000;let cursor=0,deadline=performance.now();
      while(cursor<count&&ticket===fileEpoch&&control===epoch&&running){const at=performance.now(),pcm=new Int16Array(320);
        if(at-deadline>120){cursor+=Math.floor((at-deadline)/20)*320;deadline=at;if(cursor>=count)break;}
        for(let j=0;j<320&&cursor<count;j++,cursor++){const position=cursor*ratio,low=Math.floor(position),fraction=position-low;let x=0;
          for(const channel of channels)x+=(channel[low]||0)*(1-fraction)+(channel[low+1]||0)*fraction;
          pcm[j]=Math.round(Math.max(-1,Math.min(1,x/channels.length))*32767);}
        queueSpeaker(pcm.buffer);deadline+=20;await delay(Math.max(0,deadline-performance.now()));
      }
      if(ticket===fileEpoch)$('#audio-file-name').textContent='Played · '+file.name;
    }catch(e){message(e);}finally{if(ticket===fileEpoch){playing=false;audioLabels();}}
  };
  function cardState(){const ready=usable()&&info?.sd_ready;$('#sd-empty').hidden=!!ready;$('#sd-browser').hidden=!ready;
    $('#sd-empty-title').textContent=!usable()?'Connect a robot first':info?.sd_ready===false?'No SD card':'Reading card…';
    $('#sd-capacity').textContent=ready?`${bytes(info.used||0)} / ${bytes(info.total||0)}`:'microSD · FAT32';
    $('#sd-refresh').disabled=!usable()||filesBusy;$('#sd-mount').disabled=!usable()||filesBusy;
  }
  async function refresh(mount=false){if(!usable()){cardState();return;}filesBusy=true;cardState();
    try{info=mount?await action('mount'):await (await request('/api/media/info')).json();cardState();if(info.sd_ready)await loadFiles(false);}
    catch(e){message(e);$('#sd-empty-title').textContent='Could not read card';}finally{filesBusy=false;cardState();}}
  function joined(name){return (path==='/'?'':path)+'/'+name;}
  async function loadFiles(more=false) {const requestedPath=path,requestedSession=getState().control_session;
    const result=await (await request('/api/media/files?path='+encodeURIComponent(path)+'&offset='+(more?offset:0))).json();
    if(path!==requestedPath||requestedSession!==getState().control_session)return;
    if(!more)$('#sd-rows').replaceChildren();$('#sd-path').textContent=path;next=result.next;offset=next||0;$('#sd-more').hidden=next===null||next===undefined;
    for(const file of result.entries||[]){const row=document.createElement('div');row.className='sd-row';
      const open=document.createElement('button');open.className='sd-file';const symbol=document.createElement('span');symbol.className='file-symbol';symbol.textContent=file.directory?'▱':'▤';
      const label=document.createElement('strong');label.textContent=file.name;const size=document.createElement('small');size.textContent=file.directory?'Folder':bytes(file.size);
      open.append(symbol,label,size);open.onclick=()=>{if(file.directory){path=joined(file.name);loadFiles().catch(message);}else download(joined(file.name),file.size);};row.append(open);
      const rename=document.createElement('button');rename.className='icon-button';rename.textContent='✎';rename.setAttribute('aria-label','Rename '+file.name);
      rename.onclick=()=>fileDialog('rename',joined(file.name));row.append(rename);
      if(path!=='/.cyobot-trash'&&!path.startsWith('/.cyobot-trash/')){const trash=document.createElement('button');trash.className='icon-button';trash.textContent='⌫';trash.setAttribute('aria-label','Move to trash '+file.name);
        trash.onclick=()=>fileDialog('trash',joined(file.name));row.append(trash);}$('#sd-rows').append(row);
    }
    $('#sd-list-empty').hidden=!!$('#sd-rows').children.length;
  }
  async function download(target,size){try{if(size>32*1048576)throw Error('Browser downloads are limited to 32 MB; use the SDK for larger files');
    const r=await request('/api/media/download?path='+encodeURIComponent(target)),blob=await r.blob();
    if(blob.size!==size)throw Error('Incomplete file transfer');const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=target.split('/').pop();a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  }catch(e){message(e);}}
  let dialogOp,dialogPath;function fileDialog(op,target=path){dialogOp=op;dialogPath=target;
    $('#sd-dialog-title').textContent=op==='mkdir'?'New folder':op==='trash'?'Move to trash':'Rename / move';
    $('#sd-name').hidden=op==='trash';$('#sd-name').required=op!=='trash';$('#sd-name').value=op==='rename'?target:'';
    $('#sd-dialog-hint').textContent=op==='trash'?target+' · Can be restored from trash':op==='rename'?'Destination path · also used to restore a file':'Folder name';
    $('#sd-dialog').showModal();if(op!=='trash')$('#sd-name').focus();}
  $('#sd-form').onsubmit=async e=>{e.preventDefault();const button=$('#sd-dialog-submit');button.disabled=true;
    try{const name=$('#sd-name').value.trim();const values=dialogOp==='mkdir'?{path:joined(name)}:dialogOp==='rename'?{path:dialogPath,target:name}:{path:dialogPath};
      await action(dialogOp,values);$('#sd-dialog').close();await refresh();}catch(e){message(e);}finally{button.disabled=false;}};
  $('#sd-dialog-close').onclick=()=>$('#sd-dialog').close();$('#sd-new').onclick=()=>fileDialog('mkdir');
  $('#sd-up').onclick=()=>{path=path.slice(0,path.lastIndexOf('/'))||'/';loadFiles().catch(message);};
  $('#sd-trash').onclick=()=>{path='/.cyobot-trash';loadFiles().catch(e=>{path='/';toast('Trash is empty');loadFiles().catch(message);});};
  $('#sd-more').onclick=()=>loadFiles(true).catch(message);$('#sd-refresh').onclick=()=>refresh(true);$('#sd-mount').onclick=()=>refresh(true);
  $('#sd-upload').onchange=e=>{const file=e.target.files[0];e.target.value='';if(!file)return;
    if(file.size>32*1048576){message(Error('Files must be at most 32 MB'));return;}if(!usable())return;
    const xhr=new XMLHttpRequest();xhr.open('POST','/api/media/upload?path='+encodeURIComponent(joined(file.name)));
    for(const [key,value]of Object.entries(headers()))xhr.setRequestHeader(key,value);
    const progress=$('#sd-progress');progress.hidden=false;progress.textContent='Uploading…';
    xhr.upload.onprogress=e=>{if(e.lengthComputable)progress.textContent=`${file.name} · ${Math.round(e.loaded/e.total*100)}%`;};
    xhr.timeout=120000;xhr.onload=()=>{progress.hidden=true;try{const r=JSON.parse(xhr.responseText);if(xhr.status!==200)throw Error(r.error||'Upload failed');refresh();}catch(e){message(e);}};
    xhr.onerror=xhr.ontimeout=()=>{progress.hidden=true;message(Error('File transfer interrupted · try again'));};xhr.send(file);
  };
  document.addEventListener('visibilitychange',()=>{if(document.hidden&&(running||starting))stop();});
  window.addEventListener('pagehide',localStop);
  return {open(kind){if(kind==='files')refresh();},update(){const s=getState(),key=usable()?String(s.control_session):null;
    if(key!==session){localStop();session=key;info=null;path='/';$('#sd-rows').replaceChildren();if(!$('#files-panel').hidden&&usable())refresh();}
    if(running&&performance.now()-startedAt>1200&&!s.audio?.active){localStop();if(s.audio?.error)message(Error(s.audio.error));}
    for(const id of ['#audio-listen','#audio-talk','#audio-file'])$(id).disabled=!usable()||!s.audio_ready||starting;
    if(talkPending)$('#audio-talk').disabled=true;
    $('#audio-upload-label').classList.toggle('disabled',!usable()||!s.audio_ready);
    if(!usable())$('#audio-live').textContent='Connect a robot first';
    else if(!s.audio_ready)$('#audio-live').textContent='Audio is not ready';
    const levels=s.audio?.active?s.audio.levels||[0,0]:[0,0];levels.forEach((v,i)=>{const db=20*Math.log10(Math.max(1e-5,v));$('#mic-meter-'+i).style.setProperty('--level',Math.max(0,Math.min(100,(db+90)*100/90))+'%');$('#mic-db-'+i).textContent=v>0?Math.round(db)+' dB':'— dB';});
    $('#audio-count').textContent=s.audio?.active?`${s.audio.received||0} mic · ${s.audio.sent||0} speaker`:'PCM · 2 mic / 1 speaker';cardState();
  }};
}
