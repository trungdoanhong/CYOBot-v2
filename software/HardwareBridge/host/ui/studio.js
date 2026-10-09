import * as THREE from 'three';
import { OrbitControls } from '/vendor/OrbitControls.js';
import { loadCrawler } from '/crawler-model.js';
import { createLedPanel } from '/leds.js';
import { createMediaPanel } from '/media.js';
import { createWorkspace } from '/workspace.js';
import { createRoutinePanel } from '/routines.js';
import { createEffectPanel } from '/effects.js';

const $ = (s) => document.querySelector(s), $$ = (s) => [...document.querySelectorAll(s)];
const icons = {
  fleet:'M3 3h7v7H3zM14 3h7v7h-7zM3 14h7v7H3zM14 14h7v7h-7z',
  brain:'M12 4c-3-4-8-1-7 3-4 1-4 6-1 7-1 5 5 8 8 4 3 4 9 1 8-4 3-1 3-6-1-7 1-4-4-7-7-3zM12 4v14M7 7l2 2M5 13l4-1M17 7l-2 2M19 13l-4-1',
  speaker:'M3 9h4l5-5v16l-5-5H3zM16 8a6 6 0 0 1 0 8M19 5a10 10 0 0 1 0 14',
  mic:'M9 5a3 3 0 0 1 6 0v7a3 3 0 0 1-6 0zM5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8',
  headphones:'M4 14v-3a8 8 0 0 1 16 0v3M4 12h3v8H4zM17 12h3v8h-3z',
  card:'M8 3h12v18H4V7zM8 3v4H4M8 12h8M8 16h8M11 3v4m3-4v4m3-4v4',
  trash:'M4 6h16M9 6V3h6v3M6 6l1 15h10l1-15M10 10v7m4-7v7',
  sun:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5',
  eraser:'M4 14l9-10 7 7-9 10H8zM9 9l7 7M11 21h10',rainbow:'M3 19a9 9 0 0 1 18 0M6 19a6 6 0 0 1 12 0M9 19a3 3 0 0 1 6 0',
  box:'M4 7l8-4 8 4v10l-8 4-8-4zM4 7l8 4 8-4M12 11v10', cube:'M4 7l8-4 8 4v10l-8 4-8-4zM4 7l8 4 8-4M12 11v10',
  activity:'M2 12h4l3-8 5 16 3-8h5', keyboard:'M3 6h18v12H3zM6 10h1m3 0h1m3 0h1m3 0h1M7 14h10',
  refresh:'M20 8a8 8 0 0 0-13-3L4 8m0-5v5h5M4 16a8 8 0 0 0 13 3l3-3m0 5v-5h-5',
  plus:'M12 5v14M5 12h14', minus:'M5 12h14', close:'M6 6l12 12M18 6L6 18',
  radio:'M8 8a6 6 0 0 0 0 8M16 8a6 6 0 0 1 0 8M4 4a11 11 0 0 0 0 16M20 4a11 11 0 0 1 0 16M12 10a2 2 0 1 0 0 4 2 2 0 0 0 0-4',
  mouse:'M7 8a5 5 0 0 1 10 0v8a5 5 0 0 1-10 0zM12 4v5', pause:'M8 5v14M16 5v14',
  power:'M12 3v9M7 5a8 8 0 1 0 10 0', laptop:'M4 4h16v13H4zM2 20h20',
  top:'M4 4h16v16H4zM4 8h16M8 8v12', camera:'M4 7h4l2-3h4l2 3h4v13H4zM12 10a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  grid:'M4 4h16v16H4zM4 12h16M12 4v16', sliders:'M4 7h16M4 17h16M8 4v6M16 14v6',
  wave:'M2 12c3 0 3-7 6-7s3 14 6 14 3-7 8-7', move:'M12 3v18M3 12h18M9 6l3-3 3 3M9 18l3 3 3-3M6 9l-3 3 3 3M18 9l3 3-3 3',
  battery:'M3 7h16v10H3zM21 10v4M6 10v4M9 10v4M12 10v4', wifi:'M3 8a14 14 0 0 1 18 0M6 11a10 10 0 0 1 12 0M9 14a5 5 0 0 1 6 0M12 18h.01',
  link:'M10 13a4 4 0 0 0 6 0l3-3a4 4 0 0 0-6-6l-2 2M14 11a4 4 0 0 0-6 0l-3 3a4 4 0 0 0 6 6l2-2',
  'arrow-right':'M4 12h16M14 6l6 6-6 6', 'arrow-left':'M20 12H4M10 6l-6 6 6 6', 'arrow-up':'M12 20V4M6 10l6-6 6 6', 'arrow-down':'M12 4v16M6 14l6 6 6-6',
  'rotate-left':'M4 9h5M4 9V4M4 9a8 8 0 1 1 0 8', 'rotate-right':'M20 9h-5M20 9V4M20 9a8 8 0 1 0 0 8',
  leg:'M4 5h9v5l-3 6h6v4H6v-6l3-5H4z', play:'M7 4l13 8-13 8z', crosshair:'M12 2v4M12 18v4M2 12h4M18 12h4M12 7a5 5 0 1 0 0 10 5 5 0 0 0 0-10',
  eye:'M2 12s4-7 10-7 10 7 10 7-4 7-10 7-10-7-10-7zM12 9a3 3 0 1 0 0 6 3 3 0 0 0 0-6',
  search:'M10 4a6 6 0 1 0 0 12 6 6 0 0 0 0-12M15 15l6 6', robot:'M6 5h12v10H6zM12 2v3M9 9h.01M15 9h.01M3 8v7m18-7v7M6 18l-2 3m14-3 2 3M8 15v4h8v-4'
};
function icon(name) { return `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="${icons[name] || icons.box}"/></svg>`; }
function renderIcons(root=document) { root.querySelectorAll('[data-icon]').forEach(el => { el.innerHTML=icon(el.dataset.icon); }); }
renderIcons();
$$('button').forEach(b=>{if(!b.hasAttribute('aria-label')&&b.textContent.trim())b.setAttribute('aria-label',b.textContent.trim());});

const token = $('meta[name="cyo-token"]').content;
const client = crypto.randomUUID();
let state={robots:[],connected:false,mode:'hold',joint_channels:[4,5,6,7,11,10,0,1],joints:[]};
let selectedMac=null, selectedChannel=4, mode='joint', period=2, preview=false, previewAngle=0, previewTestAt=0, pointerMoving=false;
let errorShown='', polling=false, connecting=false, heartbeatAt=0, sensorHistory=[], toastTimer, lastAngleSent=0;
const previewAngles=Array(16).fill(0);
const previewEnabled=Array(16).fill(false);
const observedAngles=new Map();
let previewWalk=null, previewTestCenter=0;

function toast(message,error=false) { clearTimeout(toastTimer); const el=$('#toast');el.textContent=message;el.className=`toast visible${error?' error':''}`;toastTimer=setTimeout(()=>el.classList.remove('visible'),3500); }
async function action(action, values={}) {
  try {
    const response=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-CYO-Token':token},body:JSON.stringify({action,client,control_session:state.control_session,...values})});
    const data=await response.json();
    if(!response.ok) throw new Error(data.error || 'Robot is not responding');
    return true;
  } catch(error) { if(action!=='heartbeat')toast(error.message,true);return false; }
}
function canControl() { return preview || (state.connected && !state.link_stale && state.owner===client); }
function physicalAngle(channel) { const mac=selectedMac||'preview';if(!observedAngles.has(mac))observedAngles.set(mac,Array(16).fill(0));const angles=observedAngles.get(mac),tick=state.telemetry?.ticks[channel];const [min,max]=state.pwm_limits||[120,600];if(tick)angles[channel]=(tick-min)*180/(max-min)-90;return angles[channel]; }
function selectChannel(channel) {
  if(channel!==selectedChannel && (previewTestAt||(state.mode==='test'&&state.owner===client)))hold();
  selectedChannel=channel;
  const joint=state.joint_channels.indexOf(channel);
  $$('[data-leg]').forEach(b=>b.classList.toggle('active',joint>=0 && +b.dataset.leg===Math.floor(joint/2)));
  $$('[data-joint]').forEach(b=>b.classList.toggle('active',joint>=0 && +b.dataset.joint===joint%2));
  $('#channel-name').textContent=`CH ${String(channel).padStart(2,'0')}`;
  const angle=preview?previewAngles[channel]:physicalAngle(channel);
  $('#angle-slider').value=Math.round(angle); updateSlider($('#angle-slider')); $('#angle-value').textContent=Math.round(angle);
  updateChannels();
}
function setMode(next) {
  drawer('servo');
  if(mode!==next && ['test','walk','routine'].includes(state.mode)) action('hold');
  routinePanel.stopPreview();
  previewTestAt=0;previewWalk=null;mode=next;
  $$('[data-mode]').forEach(b=>{b.classList.toggle('active',b.dataset.mode===mode);b.setAttribute('aria-selected',b.dataset.mode===mode);});
  $('#joint-controls').hidden=next!=='joint';$('#test-controls').hidden=next!=='test';$('#walk-controls').hidden=next!=='walk';
  $('#routine-controls').hidden=next!=='routine';$('.channel-selector').hidden=next==='routine';$('.channel-rack').hidden=next==='routine';
  $('#joint-picker').hidden=next==='walk'||next==='routine';$('#channel-title').textContent=next==='test'?'TEST CHANNEL':'SERVO';
  $('#start-test').innerHTML=icon('play')+'<span>Run test</span>';
}
function updateSlider(el) { el.style.setProperty('--fill',`${(+el.value-+el.min)/(+el.max-+el.min)*100}%`); }
$$('input[type=range]').forEach(el=>{updateSlider(el);el.addEventListener('input',()=>updateSlider(el));});
function updateChannels() {
  const ticks=preview?previewEnabled.map(on=>on?360:0):state.telemetry?.ticks||Array(16).fill(0);
  $$('#channels button').forEach(b=>{const c=+b.dataset.channel;b.classList.toggle('active',c===selectedChannel);b.classList.toggle('mapped',state.joint_channels.includes(c));b.classList.toggle('enabled',ticks[c]>0);});
  $('#active-channels').textContent=`${ticks.filter(t=>t>0).length} / 16`;
  $('#channel-power').classList.toggle('enabled',ticks[selectedChannel]>0);
}
for(let c=0;c<16;c++){const b=document.createElement('button');b.dataset.channel=c;b.textContent=String(c).padStart(2,'0');b.setAttribute('aria-label',`Servo channel ${c}`);b.onclick=()=>selectChannel(c);$('#channels').append(b);}
$$('[data-mode]').forEach(b=>b.onclick=()=>setMode(b.dataset.mode));
$$('[data-leg]').forEach(b=>b.onclick=()=>{const joint=$('[data-joint].active')?.dataset.joint||0;selectChannel(state.joint_channels[+b.dataset.leg*2 + +joint]);});
$$('[data-joint]').forEach(b=>b.onclick=()=>{const leg=$('[data-leg].active')?.dataset.leg||0;selectChannel(state.joint_channels[+leg*2 + +b.dataset.joint]);});

function sendAngle(value, force=false) {
  const angle=Math.max(-90,Math.min(90,Math.round(value)));$('#angle-value').textContent=angle;$('#angle-slider').value=angle;updateSlider($('#angle-slider'));
  if(preview){previewAngles[selectedChannel]=angle;previewEnabled[selectedChannel]=true;updateChannels();return;}
  if(!canControl())return;
  const now=performance.now();if(force||now-lastAngleSent>45){lastAngleSent=now;action('joint',{channel:selectedChannel,angle});}
}
$('#angle-slider').addEventListener('input',e=>sendAngle(+e.target.value));
$('#angle-slider').addEventListener('change',e=>sendAngle(+e.target.value,true));
$('#minus-angle').onclick=()=>sendAngle(+$('#angle-slider').value-5,true);
$('#plus-angle').onclick=()=>sendAngle(+$('#angle-slider').value+5,true);
$$('[data-angle]').forEach(b=>b.onclick=()=>sendAngle(+b.dataset.angle,true));
$('#channel-power').onclick=()=>{if(preview){hold();previewEnabled[selectedChannel]=!previewEnabled[selectedChannel];if(previewEnabled[selectedChannel])previewAngles[selectedChannel]=0;updateChannels();return;}const on=state.telemetry?.ticks[selectedChannel]>0;action(on?'channel_off':'joint',{channel:selectedChannel,angle:0});};
$('#center').onclick=()=>{if(preview){previewAngles.fill(0);previewEnabled.fill(false);state.joint_channels.forEach(c=>previewEnabled[c]=true);hold();selectChannel(selectedChannel);}else action('center');};
function hold(){routinePanel.stopPreview();previewTestAt=0;previewWalk=null;pointerMoving=false;$$('[data-direction]').forEach(b=>b.classList.remove('moving'));if(state.connected&&state.owner===client)action('hold');if(preview){$('#start-test').innerHTML=icon('play')+'<span>Run test</span>';}}
$('#hold').onclick=hold;$('#walk-hold').onclick=hold;
$('#all-off').onclick=()=>{hold();if(preview){previewEnabled.fill(false);selectChannel(selectedChannel);toast('Preview · pulses off');}else action('off');};
$('#amplitude').oninput=()=>{$('#amplitude-value').textContent=$('#amplitude').value;};
$$('[data-period]').forEach(b=>b.onclick=()=>{period=+b.dataset.period;$$('[data-period]').forEach(p=>p.classList.toggle('active',p===b));});
$('#start-test').onclick=async()=>{
  if(preview){previewTestCenter=previewAngles[selectedChannel];if(Math.abs(previewTestCenter)+ +$('#amplitude').value>90){toast('Reduce amplitude to stay within ±90°',true);return;}previewTestAt=previewTestAt?0:performance.now();previewEnabled[selectedChannel]=true;updateChannels();$('#start-test').innerHTML=icon(previewTestAt?'pause':'play')+`<span>${previewTestAt?'Hold':'Run test'}</span>`;return;}
  if(state.mode==='test'){await action('hold');return;}
  await action('test',{channel:selectedChannel,amplitude:+$('#amplitude').value,period});
};
$('#speed').oninput=()=>{$('#speed-value').textContent=$('#speed').value+'%';};
$$('[data-direction]').forEach(button=>{
  button.addEventListener('pointerdown',e=>{if(!canControl())return;e.preventDefault();button.setPointerCapture(e.pointerId);pointerMoving=true;button.classList.add('moving');const cycle=3-+$('#speed').value*.024;if(preview){previewWalk={direction:button.dataset.direction,at:performance.now(),cycle,initial:state.joint_channels.map((_,i)=>logicalAngle(i))};state.joint_channels.forEach(c=>previewEnabled[c]=true);}else action('walk',{direction:button.dataset.direction,cycle});});
  ['pointerup','pointercancel','lostpointercapture'].forEach(event=>button.addEventListener(event,()=>{if(pointerMoving)hold();}));
});
$('#connect').onclick=async()=>{
  if(connecting)return;
  if((state.connected||state.reconnecting) && state.owner===client){await action('disconnect');return;}
  if(!selectedMac){toast('Use + to find a robot',true);return;}
  routinePanel.stopPreview();effectPanel.stopPreview();preview=false;previewTestAt=0;document.body.classList.remove('previewing');
  connecting=true;updateUI();try{await action('connect',{mac:selectedMac});}finally{connecting=false;}await poll();
};
$('#scan').onclick=()=>action('scan');
$('#add-robot').onclick=()=>$('#ip-dialog').showModal();$('#close-ip').onclick=()=>$('#ip-dialog').close();
$('#ip-form').onsubmit=e=>{e.preventDefault();action('scan',{addresses:[$('#robot-ip').value.trim()]}).then(ok=>{if(ok)$('#ip-dialog').close();});};
$('#help').onclick=()=>$('#help-dialog').showModal();$('#close-help').onclick=()=>$('#help-dialog').close();
function drawer(kind){kind=kind||'servo';const changed=document.body.dataset.tool!==kind;document.body.dataset.tool=kind;
  for(const [key,panel,tab]of [['servo','servo-panel','workspace-tab'],['sensor','sensors','sensor-tab'],['led','leds','led-tab'],['audio','audio-panel','audio-tab'],['files','files-panel','files-tab']]){
    $('#'+panel).hidden=key!==kind;$('#'+tab).classList.toggle('active',key===kind);$('#'+tab).setAttribute('aria-selected',String(key===kind));$('#'+tab).tabIndex=key===kind?0:-1;
  }
  $('#tool-title').textContent=({servo:'Motion',sensor:'Observation',led:'Lighting',audio:'Audio',files:'Storage'})[kind];
  if(changed)$('.inspector-body').scrollTop=0;
  workspaceShell.setTool(kind);if(kind==='audio'||kind==='files')mediaPanel.open(kind);if(kind==='led')ledPanel.update();
}
function sensorView(on){drawer(on?'sensor':null);}
function ledView(on){drawer(on?'led':null);ledPanel.update();}
const ledPanel=createLedPanel({getState:()=>state,isPreview:()=>preview,canControl,action,toast});
const mediaPanel=createMediaPanel({getState:()=>state,client,token,toast});
const workspaceShell=createWorkspace({getState:()=>state,getSelected:()=>selectedMac,isPreview:()=>preview,client,icon,
  onSelect:mac=>{if(state.connected&&state.selected!==mac){toast('Disconnect the current robot first',true);return false;}selectedMac=mac;renderRobots();updateUI();return true;},
  onNavigate:(before,after)=>{if(before==='robot'&&after!=='robot')hold();},openTool:drawer,toast});
const routinePanel=createRoutinePanel({getState:()=>state,isPreview:()=>preview,canControl,action,hold,icon,toast,
  getAngles:()=>state.joint_channels.map((_,i)=>logicalAngle(i)),
  setAngles:angles=>state.joint_channels.forEach((c,i)=>{const j=state.joints[i]||{orientation:1,offset:0};previewAngles[c]=angles[i]*j.orientation+j.offset;previewEnabled[c]=true;})});
const effectPanel=createEffectPanel({getState:()=>state,isPreview:()=>preview,canControl,action,ledPanel,toast});
$$('[data-global-action]').forEach(button=>button.onclick=()=>button.dataset.globalAction==='hold'?hold():$('#all-off').click());
const toolTabs=[['workspace-tab','servo'],['sensor-tab','sensor'],['led-tab','led'],['audio-tab','audio'],['files-tab','files']];
toolTabs.forEach(([id,kind],index)=>{const tab=$('#'+id);tab.tabIndex=index===0?0:-1;tab.onclick=()=>drawer(kind);tab.onkeydown=e=>{
  let next;if(e.key==='ArrowRight')next=(index+1)%toolTabs.length;else if(e.key==='ArrowLeft')next=(index+toolTabs.length-1)%toolTabs.length;else if(e.key==='Home')next=0;else if(e.key==='End')next=toolTabs.length-1;else return;
  e.preventDefault();drawer(toolTabs[next][1]);$('#'+toolTabs[next][0]).focus();
};});
$$('[data-close-media]').forEach(b=>b.onclick=()=>drawer('servo'));$('#close-leds').onclick=()=>ledView(false);$('#close-sensors').onclick=()=>sensorView(false);
const imuShortcut=$('.imu-state');imuShortcut.setAttribute('role','button');imuShortcut.setAttribute('tabindex','0');imuShortcut.setAttribute('aria-label','IMU sensors');imuShortcut.title='IMU sensors';imuShortcut.onclick=()=>sensorView($('#sensors').hidden);imuShortcut.onkeydown=e=>{if(e.key==='Enter'||e.code==='Space'){e.preventDefault();e.stopPropagation();imuShortcut.click();}};
$('#preview-toggle').onclick=()=>{effectPanel.stopPreview();if(state.connected&&state.owner===client){action('disconnect');}hold();preview=!preview;document.body.classList.toggle('previewing',preview);selectChannel(selectedChannel);updateUI();};
document.addEventListener('keydown',event=>{if(/INPUT|TEXTAREA/.test(event.target.tagName)||$('dialog[open]'))return;if(event.code==='Space'){event.preventDefault();hold();}else if(event.code==='Escape'&&canControl()){$('#all-off').click();}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)hold();});
window.addEventListener('pagehide',()=>{if((state.connected||state.reconnecting)&&state.owner===client){navigator.sendBeacon('/api/action',new Blob([JSON.stringify({action:'disconnect',client,token})],{type:'application/json'}));}});

const robotArt = '<svg viewBox="0 0 64 52" aria-hidden="true"><path d="M19 17l-9-5-5 8 8 5m32-8 9-5 5 8-8 5M19 35l-8 6-6-7 8-6m32 7 8 6 6-7-8-6"/><rect x="17" y="12" width="30" height="28" rx="9"/><ellipse cx="32" cy="24" rx="12" ry="9"/><path d="M24 24h16M27 20h10M28 28h8"/></svg>';
function renderRobots(){
  const list=$('#robot-list');
  if(!state.robots.length){list.innerHTML=`<div class="empty-list">${icon('radio')}<span>${state.scanning?'Finding robots…':'No robot found'}</span></div>`;return;}
  if(!selectedMac||!state.robots.some(r=>r.mac===selectedMac))selectedMac=state.robots[0].mac;
  // DOM text nodes keep device identifiers from becoming executable HTML.
  list.replaceChildren();state.robots.forEach((r,i)=>{const b=document.createElement('button');b.className=`robot-card${r.mac===selectedMac?' selected':''}`;b.innerHTML=robotArt+'<div><strong></strong><small></small></div><span class="status-dot"></span>';b.querySelector('strong').textContent=`Crawler ${String(i+1).padStart(2,'0')}`;b.querySelector('small').textContent=r.ip;b.querySelector('.status-dot').classList.toggle('online',r.online);b.setAttribute('aria-label',`Select robot ${r.ip}`);b.onclick=()=>{if(state.connected && state.selected!==r.mac){toast('Disconnect the current robot first',true);return;}selectedMac=r.mac;renderRobots();};list.append(b);});
}
let robotListSignature='';
function updateUI(){
  ledPanel.update();
  mediaPanel.update();
  routinePanel.update();effectPanel.update();
  document.body.classList.toggle('scanning',state.scanning);
  if(state.connected&&state.selected)selectedMac=state.selected;
  if(state.telemetry)for(let c=0;c<16;c++)physicalAngle(c);
  const own=state.connected&&state.owner===client, ready=canControl();
  const signature=JSON.stringify([state.scanning,...state.robots.map(r=>[r.mac,r.ip,r.online,r.connected])]);if(signature!==robotListSignature){renderRobots();robotListSignature=signature;}
  workspaceShell.update();$$('[data-global-action]').forEach(button=>button.disabled=!ready);
  $('#connect').disabled=connecting||!selectedMac;$('#connect').classList.toggle('connected',own);
  const recovering=state.reconnecting&&state.owner===client;
  $('#connect').innerHTML=icon(own?'wifi':'link')+`<span>${connecting?'Connecting…':recovering?'Reconnecting…':own?'Connected':state.connected?'In use in another window':'Connect robot'}</span>`+icon(own||recovering?'close':'arrow-right');
  $('#connect').setAttribute('aria-label',own||recovering?'Disconnect robot':'Connect robot');
  $('#connect').title=own?'Disconnect · hold last angles':'Connect robot';
  $('#connection-dot').classList.toggle('online',own);
  $('#connection-label').textContent=recovering?'Reconnecting · holding':own&&state.link_stale?'Waiting for feedback · holding':own?state.robots.find(r=>r.mac===state.selected)?.ip||'Connected':preview?'Preview · PC only':'Select a robot to connect';
  const robotIndex=Math.max(0,state.robots.findIndex(r=>r.mac===selectedMac));$('#robot-title').innerHTML=`Crawler <span>${String(robotIndex+1).padStart(2,'0')}</span>`;
  $('#scene-mode').textContent=preview?'3D preview':own?'Live connection':'3D preview';
  $('#control-badge').textContent=preview?'PREVIEW':recovering?'RECONNECT':own?(state.link_stale?'HOLD':state.mode==='test'?'TEST':state.mode==='walk'?'MOVING':state.mode==='routine'?'ROUTINE':'LIVE'):'STANDBY';
  $('#control-badge').className='mode-badge'+(own?' live':'')+(state.mode==='test'||preview?' testing':'');
  const s=state.telemetry;$('#battery').textContent=s?s.battery_v.toFixed(2):'—';$('#latency').textContent=state.rtt_ms===null||state.rtt_ms===undefined?'—':Math.round(state.rtt_ms);
  $('#imu-dot').classList.toggle('active',!!(s?.flags&8));$('#button-left').classList.toggle('pressed',!!(s?.buttons&1));$('#button-right').classList.toggle('pressed',!!(s?.buttons&2));
  $('#footer-state').textContent=preview?'3D preview':own?state.mode==='walk'?'Moving':state.mode==='test'?'Testing servo':state.mode==='routine'?'Running routine':'Robot ready':'Ready';
  ['#angle-slider','#minus-angle','#plus-angle','#channel-power','#center','#hold','#all-off','#start-test'].forEach(selector=>$(selector).disabled=!ready);
  const testing=preview?!!previewTestAt:state.mode==='test';$('#amplitude').disabled=testing;$$('[data-period]').forEach(b=>b.disabled=testing);
  $$('[data-angle],[data-direction]').forEach(b=>b.disabled=!ready);
  if(!preview){$('#start-test').classList.toggle('running',state.mode==='test');$('#start-test').innerHTML=icon(state.mode==='test'?'pause':'play')+`<span>${state.mode==='test'?'Hold':'Run test'}</span>`;}
  $('#start-test').setAttribute('aria-label',$('#start-test').textContent.trim());
  updateChannels();
  if(mode==='joint'&&!preview && document.activeElement!==$('#angle-slider')){
    const angle=Math.round(physicalAngle(selectedChannel));$('#angle-value').textContent=angle;$('#angle-slider').value=angle;updateSlider($('#angle-slider'));
  }
  if(state.error && state.error!==errorShown){toast(state.error,true);errorShown=state.error;}
  if(!state.error)errorShown='';
  if(s&&state.connected&&!preview){
    if(!state.link_stale){sensorHistory.push({a:s.accel_g,g:s.gyro_dps});if(sensorHistory.length>80)sensorHistory.shift();}
    $('#accel-values').textContent=s.accel_g.map((v,i)=>`${'XYZ'[i]} ${v.toFixed(2)}`).join('  ');$('#gyro-values').textContent=s.gyro_dps.map((v,i)=>`${'XYZ'[i]} ${v.toFixed(1)}`).join('  ');
    $('#sensor-status').textContent=state.link_stale?'Waiting for IMU data':s.flags&8?'LSM6DSL · LIVE':'IMU is not responding';
  }else{sensorHistory=[];$('#sensor-status').textContent='Connect a robot to view IMU data';$('#accel-values').textContent='—';$('#gyro-values').textContent='—';}
}
async function poll(){
  if(polling)return;polling=true;
  try{const response=await fetch('/api/state');if(!response.ok)throw Error();state=await response.json();updateUI();if(!document.hidden&&(state.connected||state.reconnecting)&&state.owner===client&&performance.now()-heartbeatAt>180){heartbeatAt=performance.now();await action('heartbeat');}}
  catch{if(state.connected){state.connected=false;updateUI();toast('Studio connection interrupted',true);}}finally{polling=false;}
}
setInterval(poll,120);poll();updateUI();

// Original assembled crawler URDF and STL geometry, with live commanded joints.
const viewport=$('#viewport'), scene=new THREE.Scene();
let renderer;
try{renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,preserveDrawingBuffer:true});}
catch(error){$('#viewport-loader').innerHTML='This browser does not support 3D';throw error;}
renderer.setPixelRatio(Math.min(devicePixelRatio,1.8));renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;
renderer.outputColorSpace=THREE.SRGBColorSpace;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.85;viewport.prepend(renderer.domElement);
const camera=new THREE.PerspectiveCamera(36,1,.1,100);camera.position.set(7,6.2,8);
const controls=new OrbitControls(camera,renderer.domElement);controls.target.set(0,1.1,0);controls.enableDamping=true;controls.dampingFactor=.075;controls.minDistance=5.8;controls.maxDistance=16;controls.maxPolarAngle=Math.PI/2.05;controls.enablePan=false;
scene.add(new THREE.HemisphereLight(0xfafef5,0x93a089,1.3));
const key=new THREE.DirectionalLight(0xfff8e9,3.0);key.position.set(-3,9,5);key.castShadow=true;key.shadow.mapSize.set(2048,2048);Object.assign(key.shadow.camera,{left:-6,right:6,top:6,bottom:-6,near:1,far:25});key.shadow.bias=-.0003;key.shadow.normalBias=.02;scene.add(key);
const fill=new THREE.DirectionalLight(0xe5f4ec,1.2);fill.position.set(5,3,-4);scene.add(fill);
function mesh(geometry,material,parent,x=0,y=0,z=0){const m=new THREE.Mesh(geometry,material);m.position.set(x,y,z);m.castShadow=true;m.receiveShadow=true;parent.add(m);return m;}
function cylinder(radius,height,material,parent,x=0,y=0,z=0){return mesh(new THREE.CylinderGeometry(radius,radius,height,64),material,parent,x,y,z);}
function ring(radius,tube,material,parent,x=0,y=0,z=0){const m=mesh(new THREE.TorusGeometry(radius,tube,10,90),material,parent,x,y,z);m.rotation.x=-Math.PI/2;return m;}
const floor=mesh(new THREE.PlaneGeometry(100,100),new THREE.ShadowMaterial({opacity:.14}),scene,0,-.12,0);floor.rotation.x=-Math.PI/2;floor.castShadow=false;
const grid=new THREE.GridHelper(40,80,0xd6dfcb,0xe1e7d8);grid.position.y=-.115;grid.material.transparent=true;grid.material.opacity=.52;scene.add(grid);
const podium=cylinder(3.18,.065,new THREE.MeshStandardMaterial({color:0xf0f2e7,roughness:.88}),scene,0,-.081,0);podium.castShadow=false;
ring(3.08,.009,new THREE.MeshStandardMaterial({color:0xd5dccd,roughness:1}),scene,0,-.045,0);
const root=new THREE.Group();scene.add(root);
const picks=[],pins=[];
let crawler=null,modelError='',selectedModelJoint=-2;
viewport.dataset.modelState=JSON.stringify({ready:false});
loadCrawler(root,progress=>{$('#viewport-loader').lastChild.textContent=`Loading 3D · ${progress}%`;}).then(model=>{
  crawler=model;picks.push(...model.picks);
  model.joints.forEach((joint,index)=>{
    const pin=document.createElement('button');pin.className='joint-pin';pin.setAttribute('aria-label',`Select joint ${index%2?'knee':'hip'} ${Math.floor(index/2)+1}`);pin.textContent=`${Math.floor(index/2)+1}${index%2?'B':'A'}`;
    pin.onclick=()=>{setMode('joint');selectChannel(state.joint_channels[index]);};$('#joint-labels').append(pin);pins.push({pin,pick:joint});
  });
  $('#viewport-loader').hidden=true;
}).catch(error=>{modelError=error.message;$('#viewport-loader').textContent='Could not load model · reload the page';toast(modelError,true);});
let fitScale=1;
function resize(){const w=viewport.clientWidth,h=viewport.clientHeight;if(!w||!h)return;renderer.setSize(w,h,false);camera.aspect=w/h;camera.updateProjectionMatrix();const next=Math.max(1,1.05/camera.aspect);camera.position.sub(controls.target).multiplyScalar(next/fitScale).add(controls.target);controls.minDistance=5.8*next;controls.maxDistance=16*next;fitScale=next;}
new ResizeObserver(resize).observe(viewport);resize();
$('#reset-view').onclick=()=>{controls.target.set(0,1.1,0);camera.position.set(7,6.2,8).sub(controls.target).multiplyScalar(fitScale).add(controls.target);controls.update();};
$('#top-view').onclick=()=>{camera.position.set(.01,10*fitScale,.01);controls.target.set(0,.4,0);controls.update();};
$('#grid-toggle').onclick=()=>{grid.visible=!grid.visible;};
$('#capture').onclick=()=>{renderer.render(scene,camera);const a=document.createElement('a');a.download='cyobot-studio.png';a.href=renderer.domElement.toDataURL('image/png');a.click();};
const raycaster=new THREE.Raycaster(), mouse=new THREE.Vector2();let downPoint;
renderer.domElement.addEventListener('pointerdown',e=>{downPoint=[e.clientX,e.clientY];});
renderer.domElement.addEventListener('pointerup',e=>{if(!downPoint||Math.hypot(e.clientX-downPoint[0],e.clientY-downPoint[1])>5)return;const r=renderer.domElement.getBoundingClientRect();mouse.set((e.clientX-r.left)/r.width*2-1,-(e.clientY-r.top)/r.height*2+1);raycaster.setFromCamera(mouse,camera);const hit=raycaster.intersectObjects(picks)[0];if(hit){setMode('joint');selectChannel(state.joint_channels[hit.object.userData.joint]);}});
const position=new THREE.Vector3();
function logicalAngle(index){const channel=state.joint_channels[index];const joint=state.joints[index];const physical=preview?previewAngles[channel]:physicalAngle(channel);return joint?(physical-joint.offset)/joint.orientation:physical;}
function chart(canvas,field,range){const context=canvas.getContext('2d');const w=canvas.clientWidth,h=canvas.clientHeight;if(!w||!h)return;canvas.width=w*devicePixelRatio;canvas.height=h*devicePixelRatio;context.scale(devicePixelRatio,devicePixelRatio);context.clearRect(0,0,w,h);context.strokeStyle='#e2e8d9';context.lineWidth=1;for(const y of [h*.25,h*.5,h*.75]){context.beginPath();context.moveTo(0,y);context.lineTo(w,y);context.stroke();}['#799a66','#bd9673','#85a1a8'].forEach((color,axis)=>{context.strokeStyle=color;context.lineWidth=1.5;context.beginPath();sensorHistory.forEach((sample,i)=>{const x=i/79*w,y=h/2-sample[field][axis]/range*h*.43;if(i===0)context.moveTo(x,y);else context.lineTo(x,y);});context.stroke();});}
let lastChart=0,lastModelState=0,previousFrame=performance.now();
function animate(now){
  requestAnimationFrame(animate);
  if($('#robot-space').hidden||document.hidden){previousFrame=now;return;}
  if(preview)routinePanel.tick(now);
  if(previewTestAt){previewAngles[selectedChannel]=previewTestCenter+ +$('#amplitude').value*Math.sin((now-previewTestAt)*Math.PI*2/(period*1000));$('#angle-value').textContent=Math.round(previewAngles[selectedChannel]);}
  if(previewWalk){const p=previewWalk,phases=state.gait_phases?.[p.direction];if(phases){const t=(now-p.at)/(p.cycle*250),step=Math.floor(t),fraction=t-step,before=step===0?p.initial:phases[(step-1)%4],after=phases[step%4];state.joint_channels.forEach((c,i)=>{const j=state.joints[i]||{orientation:1,offset:0};previewAngles[c]=(before[i]+(after[i]-before[i])*fraction)*j.orientation+j.offset;});}}
  if(crawler){crawler.pose(state.joint_channels.map((_,i)=>logicalAngle(i)),(now-previousFrame)/1000);const selected=state.joint_channels.indexOf(selectedChannel);if(selected!==selectedModelJoint){crawler.highlight(selected);selectedModelJoint=selected;}}
  previousFrame=now;
  // Approximate pitch/roll from gravity; do not integrate an invented yaw.
  const accel=state.telemetry?.accel_g;let pitch=0,roll=0;
  if(!preview&&accel && (state.telemetry.flags&8)){roll=Math.atan2(accel[1],accel[2]);pitch=Math.atan2(-accel[0],Math.hypot(accel[1],accel[2]));}
  root.rotation.x=THREE.MathUtils.lerp(root.rotation.x,THREE.MathUtils.clamp(roll,-.35,.35),.05);root.rotation.z=THREE.MathUtils.lerp(root.rotation.z,THREE.MathUtils.clamp(pitch,-.35,.35),.05);
  controls.update();scene.updateMatrixWorld();
  pins.forEach(({pin,pick})=>{pick.getWorldPosition(position);position.y+=.13;position.project(camera);pin.style.left=`${(position.x*.5+.5)*viewport.clientWidth}px`;pin.style.top=`${(-position.y*.5+.5)*viewport.clientHeight}px`;pin.hidden=mode==='walk'||position.z>1||position.x<-1||position.x>1||position.y<-1||position.y>1;pin.classList.toggle('active',state.joint_channels[pick.userData.joint]===selectedChannel);});
  renderer.render(scene,camera);
  if(now-lastModelState>500){lastModelState=now;viewport.dataset.modelState=JSON.stringify(crawler?{ready:true,...crawler.diagnostics()}:{ready:false,error:modelError});}
  if(now-lastChart>130&&!$('#sensors').hidden){lastChart=now;chart($('#accel-chart'),'a',1.7);const gyroRange=Math.max(8,...sensorHistory.flatMap(s=>s.g.map(Math.abs)));chart($('#gyro-chart'),'g',gyroRange);$('#attitude-horizon').style.transform=`rotate(${roll*180/Math.PI}deg) translateY(${pitch*45}px)`;$('#tilt-values').textContent=state.connected&&!preview&&(state.telemetry?.flags&8)?`${(roll*180/Math.PI).toFixed(1)}° / ${(pitch*180/Math.PI).toFixed(1)}°`:'—';}
}
requestAnimationFrame(animate);
