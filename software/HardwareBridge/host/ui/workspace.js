// Workspace navigation and presentation derive from the shared Studio snapshot.
// This module never sends movement commands or acquires robot sessions.
const $=selector=>document.querySelector(selector);
const $$=selector=>[...document.querySelectorAll(selector)];
function label(el,value){if(el.textContent!==String(value))el.textContent=value;}
export function connectionState(state,client,preview=false){
  if(state.reconnecting&&state.owner===client)return {tone:'waiting',label:'Reconnecting',detail:'Hold last angles',ready:false};
  if(state.connected&&state.owner!==client)return {tone:'waiting',label:'Another window has control',detail:'Read only',ready:false};
  if(state.connected&&state.link_stale)return {tone:'waiting',label:'Waiting for feedback',detail:'Hold last angles',ready:false};
  if(state.connected)return {tone:'live',label:'Connected',detail:'Manual control',ready:true};
  if(preview)return {tone:'preview',label:'Preview',detail:'PC simulation',ready:true};
  return {tone:state.error?'error':'idle',label:state.error?'Connection failed':'Not connected',detail:'Select a robot to begin',ready:false};
}
export function toolState(tool,state,client,preview=false){
  const c=connectionState(state,client,preview);
  if(preview&&!state.connected)return ['servo','led'].includes(tool)?{tone:'preview',label:'Preview'}:{tone:'idle',label:'Robot connection required'};
  if(!c.ready)return {tone:c.tone,label:state.connected&&state.owner!==client?'Read only':c.label};
  if(tool==='sensor')return state.telemetry?.flags&8?{tone:'live',label:'Live'}:{tone:'error',label:'No data'};
  if(tool==='led')return !state.leds_supported?{tone:'idle',label:'Not supported'}:state.leds_pending?{tone:'waiting',label:'Sending'}:state.error?.startsWith('LED')?{tone:'error',label:'Retry needed'}:{tone:'live',label:'Ready'};
  if(tool==='audio')return !state.audio_ready?{tone:'idle',label:'Not ready'}:state.audio?.error?{tone:'error',label:'Stream error'}:state.audio?.active?{tone:'live',label:'Live'}:{tone:'idle',label:'Ready'};
  if(tool==='files')return state.sd_ready?{tone:'live',label:'Card mounted'}:{tone:'waiting',label:'No SD card'};
  return {tone:'live',label:state.mode==='test'?'Test servo':state.mode==='walk'?'Moving':state.mode==='routine'?'Running routine':'Holding pose'};
}
function pill(el,value){label(el,value.label);el.dataset.tone=value.tone;}
export function createWorkspace({getState,getSelected,isPreview,client,icon,onSelect,onNavigate,openTool,toast}){
  let space='robot',signature='',tool='servo';
  function navigate(next){if(!['fleet','robot','brain'].includes(next))return;
    if(next!==space)onNavigate(space,next);space=next;document.body.dataset.space=space;
    $$('[data-app-view]').forEach(view=>view.hidden=view.dataset.appView!==space);
    $$('[data-space]').forEach(button=>{button.classList.toggle('active',button.dataset.space===space);
      if(button.dataset.space===space)button.setAttribute('aria-current','page');else button.removeAttribute('aria-current');});
    update();
  }
  $$('[data-space]').forEach(button=>button.onclick=()=>navigate(button.dataset.space));
  $$('[data-open-tool]').forEach(button=>button.onclick=()=>{navigate('robot');openTool(button.dataset.openTool);});
  $('#fleet-scan').onclick=()=>$('#scan').click();$('#fleet-add').onclick=()=>$('#add-robot').click();
  $('#brain-guide').onclick=()=>$('#brain-dialog').showModal();$('#brain-guide-close').onclick=()=>$('#brain-dialog').close();
  $('#brain-export').onclick=()=>{const s=getState();if(!s.telemetry){toast('Connect a robot to export observations',true);return;}
    const sample={schema:'cyobot-observation-v1',time:new Date().toISOString(),mac:s.selected,
      telemetry:s.telemetry,leds:s.leds,audio:s.audio?.active?{sample_rate:16000,mic_channels:2,levels:s.audio.levels}:null};
    const url=URL.createObjectURL(new Blob([JSON.stringify(sample,null,2)],{type:'application/json'}));
    const a=document.createElement('a');a.href=url;a.download='cyobot-observation.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);
  };
  function fleetCards(state){const selected=getSelected(),robots=state.robots||[];
    const key=JSON.stringify([selected,state.scanning,state.connected,state.selected,...robots.map(r=>[r.mac,r.ip,r.online,r.flags])]);if(key===signature)return;signature=key;
    $('#fleet-grid').replaceChildren();$('#fleet-empty').hidden=robots.length>0;
    for(const [i,r]of robots.entries()){
      const card=document.createElement('article');card.className='fleet-card'+(selected===r.mac?' selected':'');
      card.innerHTML=`<div class="fleet-card-top"><span class="fleet-number"></span><span class="status-pill"></span></div><div class="fleet-robot-art">${icon('robot')}</div><h2></h2><div class="fleet-address"></div><div class="fleet-capabilities"></div><button class="ui-button primary">${icon('arrow-right')}<span>Open robot</span></button>`;
      card.querySelector('.fleet-number').textContent=String(i+1).padStart(2,'0');card.querySelector('h2').textContent=`Crawler ${String(i+1).padStart(2,'0')}`;
      card.querySelector('.fleet-address').textContent=r.ip;
      pill(card.querySelector('.status-pill'),!r.online?{tone:'idle',label:'Offline'}:r.flags&16?{tone:'error',label:'Board fault'}:state.connected&&state.selected===r.mac?{tone:'live',label:'Connecting'}:{tone:'idle',label:'Discovered'});
      const capabilities=card.querySelector('.fleet-capabilities');
      for(const [mask,glyph,label]of [[4,'sliders','Servo'],[8,'activity','IMU'],[64,'sun','LED'],[256,'mic','Audio'],[128,'card','SD card']]){
        const b=document.createElement('span');b.innerHTML=icon(glyph);b.title=label+(r.flags&mask?' · available':' · unavailable');b.setAttribute('aria-label',b.title);b.classList.toggle('available',!!(r.flags&mask));capabilities.append(b);
      }
      card.querySelector('button').onclick=()=>{if(onSelect(r.mac)!==false)navigate('robot');};$('#fleet-grid').append(card);
    }
  }
  function update(){const s=getState(),c=connectionState(s,client,isPreview()),selected=s.robots?.find(r=>r.mac===getSelected());
    pill($('#session-label'),c);$('#session-orb').dataset.tone=c.tone;
    label($('#session-detail'),s.connected?`${s.robots.find(r=>r.mac===s.selected)?.ip||''} · ${c.detail}`:selected?selected.ip:c.detail);
    label($('#session-mode'),s.connected&&s.mode==='test'?'Test servo':s.connected&&s.mode==='walk'?'Drive':s.connected&&s.mode==='routine'?'Routine':isPreview()?'Preview':'Manual');
    $('#fleet-total').textContent=s.robots?.length||0;$('#fleet-online').textContent=s.robots?.filter(r=>r.online).length||0;$('#fleet-active').textContent=s.connected?1:0;
    $('#fleet-scan').disabled=!!s.scanning;$('#fleet-scan-label').textContent=s.scanning?'Scanning…':'Scan robots';
    fleetCards(s);pill($('#tool-status'),toolState(tool,s,client,isPreview()));
    const i=Math.max(0,s.robots?.findIndex(r=>r.mac===getSelected())??0);$('#inspector-title').textContent=`CRAWLER ${String(i+1).padStart(2,'0')}`;
    const telemetry=s.telemetry;
    $('#brain-robot').textContent=s.connected?`Crawler ${String(i+1).padStart(2,'0')}`:'Select robot';
    $('#brain-imu').textContent=telemetry?.flags&8?'Live IMU':'IMU unavailable';
    $('#brain-mic').textContent=s.audio?.active?'Live microphones':'Microphones off';
    $('#brain-imu').closest('button').setAttribute('aria-label',$('#brain-imu').textContent);
    $('#brain-mic').closest('button').setAttribute('aria-label',$('#brain-mic').textContent);
    $('#brain-output').textContent=telemetry?`${telemetry.ticks.filter(t=>t>0).length} / 16 channels enabled`:'No robot connected';
    $('#brain-age').textContent=telemetry?`${s.age_ms??'—'} ms`:'—';
    $('#brain-export').disabled=!telemetry;$('#brain-pwm').textContent=s.connected?s.mode==='hold'?'Holding pose':s.mode==='walk'?'Moving':s.mode==='routine'?'Running routine':'Test servo':'Not connected';
    $('#brain-pipeline').classList.toggle('receiving',!!telemetry);$('#brain-pipeline').classList.toggle('listening',!!s.audio?.active);
  }
  update();return {update,navigate,setTool(next){tool=next;update();},get space(){return space;}};
}
