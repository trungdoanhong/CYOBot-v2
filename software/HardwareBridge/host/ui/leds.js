// The two physical PCB views: RESET/LED0 at the top; USB at the bottom.
export const MATRIX_ROWS = [[0,1,2,3,4],[5,6,7,8,9,10,11],[12,13,14,15,16,17,18,19,20],[21,22,23,24,25,26,27],[28,29,30,31,32]];
export const CHARACTER_PIXELS = [0,1,2,3,4,6,7,8,9,10,14,15,16,17,18,22,23,24,25,26,28,29,30,31,32];
const blank=n=>Array.from({length:n},()=>[0,0,0]);
const hex=c=>'#'+c.map(x=>x.toString(16).padStart(2,'0')).join('');
const rgb=h=>[1,3,5].map(i=>parseInt(h.slice(i,i+2),16));
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);

export function createLedPanel({getState,isPreview,canControl,action,toast}) {
  const $=s=>document.querySelector(s), all=s=>[...document.querySelectorAll(s)];
  const drafts=new Map();let target='matrix',eraser=false,painting=false,timer,key='',draft;
  function currentKey(){return isPreview()?'preview':getState().selected||'disconnected';}
  function ready(){return isPreview()||(canControl()&&getState().leds_supported&&!!getState().leds);}
  function wire(){const scale=draft.brightness/100;return Object.fromEntries(['matrix','ring'].map(k=>[k,draft[k].map(p=>p.map(c=>Math.round(c*scale)))]));}
  function paint(group,index){if(!ready())return;draft[group][index]=eraser?[0,0,0]:rgb($('#led-color').value);changed();}
  function changed(){draft.dirty=true;draft.failed=false;render();clearTimeout(timer);timer=setTimeout(send,100);}
  async function send(){
    if(!ready()||isPreview())return;
    const sentDraft=draft, sent=wire();sentDraft.failed=false;
    sentDraft.failed=!await action('leds',sent);
    render();
  }
  function groups(){return target==='both'?['matrix','ring']:[target];}
  function pixel(group,index,parent){const b=document.createElement('button');b.className='led-pixel';b.dataset.ledGroup=group;b.dataset.ledIndex=index;b.textContent=index;b.title=`${group==='matrix'?'Matrix':'Ring'} · LED ${index}`;b.setAttribute('aria-label',b.title);b.setAttribute('aria-pressed','false');b.onclick=()=>paint(group,index);parent.append(b);return b;}
  for(const indices of MATRIX_ROWS){const row=document.createElement('div');row.className='led-row';for(const i of indices)pixel('matrix',i,row);$('#led-matrix').append(row);}
  for(let i=0;i<12;i++){const b=pixel('ring',i,$('#led-ring')),a=i*Math.PI/6;b.style.left=`${50+43*Math.sin(a)}%`;b.style.top=`${50-43*Math.cos(a)}%`;}
  const surfaces=['#led-matrix','#led-ring'];
  for(const s of surfaces){$(s).addEventListener('pointerdown',e=>{const b=e.target.closest('.led-pixel');if(b&&ready()){e.preventDefault();painting=true;paint(b.dataset.ledGroup,+b.dataset.ledIndex);}});$(s).addEventListener('pointermove',e=>{if(!painting)return;const b=document.elementFromPoint(e.clientX,e.clientY)?.closest('.led-pixel');if(b)paint(b.dataset.ledGroup,+b.dataset.ledIndex);});}
  window.addEventListener('pointerup',()=>painting=false);window.addEventListener('pointercancel',()=>painting=false);document.addEventListener('visibilitychange',()=>painting=false);
  all('[data-led-target]').forEach(b=>b.onclick=()=>{target=b.dataset.ledTarget;all('[data-led-target]').forEach(x=>x.classList.toggle('active',x===b));});
  const swatches=['#53d99b','#55baff','#bd80ff','#ff7598','#ffb74d','#ffffff'];
  for(const c of swatches){const b=document.createElement('button');b.className='led-swatch';b.style.background=c;b.setAttribute('aria-label',`Color ${c}`);b.onclick=()=>{$('#led-color').value=c;eraser=false;render();};$('#led-swatches').append(b);}
  $('#led-color').oninput=()=>{eraser=false;render();};
  $('#led-eraser').onclick=()=>{eraser=!eraser;render();};
  $('#led-retry').onclick=send;
  $('#led-brightness').oninput=e=>{if(!ready())return;draft.brightness=+e.target.value;changed();};
  $('#led-fill').onclick=()=>{if(!ready())return;for(const g of groups())draft[g]=Array.from({length:g==='matrix'?33:12},()=>rgb($('#led-color').value));changed();};
  $('#led-clear').onclick=()=>{if(!ready())return;for(const g of groups())draft[g]=blank(g==='matrix'?33:12);changed();};
  all('[data-led-preset]').forEach(b=>b.onclick=()=>{
    if(!ready())return;
    const color=rgb($('#led-color').value),type=b.dataset.ledPreset;
    for(const g of groups()){
      const n=g==='matrix'?33:12;draft[g]=blank(n);
      if(type==='rainbow'){for(let i=0;i<n;i++){const hue=i/n*6;draft[g][i]=[0,2,4].map(k=>Math.round(255*Math.max(0,Math.min(1,Math.abs((hue+k)%6-3)-1))));}}
      else if(g==='ring'){for(const i of (type==='heart'?[0,1,2,3,4,5,6,7,8,9,10,11]:[2,3,4,5,6,7,8,9,10]))draft[g][i]=[...color];}
      else {const indices=type==='heart'?[5,1,6,7,3,8,9,10,11,12,13,14,16,17,18,22]:[6,8,15,19,21,22,23];for(const i of indices)draft[g][CHARACTER_PIXELS[i]]=[...color];}
    }
    changed();
  });
  function render(){
    if(!draft)return;
    const s=getState(),enabled=ready();
    all('.led-pixel').forEach(b=>{const c=draft[b.dataset.ledGroup][+b.dataset.ledIndex],on=c.some(x=>x>0)&&draft.brightness>0;b.style.setProperty('--led-color',hex(c));b.classList.toggle('lit',on);b.setAttribute('aria-pressed',String(on));b.disabled=!enabled;});
    $('#led-eraser').classList.toggle('active',eraser);
    $('#led-brightness').value=draft.brightness;$('#led-brightness-value').textContent=draft.brightness+'%';
    all('#leds input,#led-fill,#led-clear,#led-eraser,#led-retry,[data-led-preset],.led-swatch').forEach(b=>b.disabled=!enabled);
    $('#led-retry').hidden=!draft.failed;
    $('#led-status').textContent=isPreview()?'Preview · PC only':!s.connected?'Connect a robot to control it':!s.leds_supported?'LED firmware required':!s.leds?'Reading LEDs…':draft.failed?'Send failed · retry':draft.dirty||s.leds_pending?'Sending…':'Confirmed by board';
    $('#led-status').classList.toggle('confirmed',enabled&&!draft.dirty&&!draft.failed&&!isPreview());
  }
  function update(){
    const next=currentKey(),s=getState();
    if(next!==key||!draft){if(draft?.dirty&&key!=='preview')draft.failed=true;clearTimeout(timer);key=next;if(!drafts.has(key))drafts.set(key,{matrix:blank(33),ring:blank(12),brightness:20,dirty:false,loaded:false,failed:false});draft=drafts.get(key);}
    if(!isPreview()&&s.leds){
      if(!draft.loaded){draft.matrix=s.leds.matrix.map(p=>[...p]);draft.ring=s.leds.ring.map(p=>[...p]);if([...draft.matrix,...draft.ring].some(p=>p.some(c=>c)))draft.brightness=100;draft.loaded=true;}
      if(draft.dirty&&equal(wire(),{matrix:s.leds.matrix,ring:s.leds.ring})){draft.dirty=false;draft.failed=false;}
      if(!draft.dirty&&!equal(wire(),{matrix:s.leds.matrix,ring:s.leds.ring})){draft.matrix=s.leds.matrix.map(p=>[...p]);draft.ring=s.leds.ring.map(p=>[...p]);draft.brightness=100;}
      if(draft.dirty&&!s.leds_pending&&s.error?.startsWith('LED'))draft.failed=true;
    }
    if(!$('#leds').hidden)render();
  }
  update();return {update,showPreview(frame){if(!isPreview())return;draft.matrix=frame.matrix.map(p=>[...p]);draft.ring=frame.ring.map(p=>[...p]);draft.brightness=100;draft.dirty=false;render();}};
}
