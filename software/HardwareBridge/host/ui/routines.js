const $=s=>document.querySelector(s);
export function sampleRoutine(frames,initial,elapsed,speed=1,repeats=1){
  let remaining=Math.max(0,elapsed)*speed,before=initial;
  for(let cycle=0;cycle<repeats;cycle++)for(const frame of frames){
    if(remaining<frame.seconds){const t=remaining/frame.seconds,k=t*t*(3-2*t);return before.map((a,i)=>a+(frame.angles[i]-a)*k);}
    remaining-=frame.seconds;before=frame.angles;
  }return [...before];
}
export function createRoutinePanel({getState,isPreview,canControl,action,hold,getAngles,setAngles,icon,toast}){
  let catalog={},selected='bow',previewRun=null;
  fetch('/routines.json').then(r=>{if(!r.ok)throw Error('Could not load routines');return r.json();}).then(data=>{
    catalog=data;for(const [id,entry]of Object.entries(catalog)){
      const b=document.createElement('button');b.dataset.routine=id;b.innerHTML=icon(entry.icon)+'<span></span>';b.querySelector('span').textContent=entry.label;
      b.onclick=()=>{hold();selected=id;update();};$('#routine-grid').append(b);
    }update();
  }).catch(e=>toast(e.message,true));
  const running=()=>isPreview()?!!previewRun:getState().mode==='routine';
  $('#routine-run').onclick=async()=>{
    if(running()){hold();return;}
    if(!canControl()||!catalog[selected])return;
    const speed=+$('#routine-speed').value,repeats=+$('#routine-repeats').value;
    if(isPreview())previewRun={name:selected,at:performance.now(),initial:getAngles(),speed,repeats};
    else await action('routine',{name:selected,speed,repeats});update();
  };
  $('#routine-speed').oninput=()=>$('#routine-speed-value').textContent=(+$('#routine-speed').value).toFixed(1)+'×';
  function duration(name,speed,repeats){return catalog[name]?.frames.reduce((s,f)=>s+f.seconds,0)*repeats/speed||0;}
  function update(){const active=running(),s=getState(),run=isPreview()?previewRun:s.routine;
    if(run?.name)selected=run.name;
    document.querySelectorAll('[data-routine]').forEach(b=>{b.classList.toggle('active',b.dataset.routine===selected);b.setAttribute('aria-pressed',String(b.dataset.routine===selected));});
    $('#routine-run').disabled=!canControl()||!catalog[selected];$('#routine-run').innerHTML=icon(active?'pause':'play')+'<span>'+(active?'Hold':isPreview()?'Preview routine':'Run routine')+'</span>';
    $('#routine-run').setAttribute('aria-label',active?'Hold routine':isPreview()?'Preview routine':'Run routine');
    $('#routine-speed').disabled=$('#routine-repeats').disabled=active;
    const total=duration(selected,+$('#routine-speed').value,+$('#routine-repeats').value);
    $('#routine-duration').textContent=total.toFixed(1)+' s';
    const progress=active?(isPreview()?(performance.now()-previewRun.at)/1000/duration(selected,previewRun.speed,previewRun.repeats):run?.progress||0):0;
    $('#routine-progress').value=Math.min(1,progress);
    $('#routine-caption').textContent=active?(isPreview()?'Preview · PC only':'Running on robot'):'8 crawler joints · finite sequence';
  }
  return {update,stopPreview(){previewRun=null;},tick(now){if(!previewRun)return;
    const p=previewRun,elapsed=(now-p.at)/1000;setAngles(sampleRoutine(catalog[p.name].frames,p.initial,elapsed,p.speed,p.repeats));
    if(elapsed>=duration(p.name,p.speed,p.repeats))previewRun=null;
  }};
}
