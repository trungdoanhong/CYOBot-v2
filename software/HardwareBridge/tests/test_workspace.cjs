// Presentation must not advertise a usable live tool during a stale/foreign lease.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const source = fs.readFileSync(path.join(__dirname, '../host/ui/workspace.js'));
  const {connectionState, toolState} = await import('data:text/javascript;base64,' + source.toString('base64'));
  const active = {connected:true, owner:'this-window', telemetry:{flags:8}, leds_supported:true, audio_ready:true, sd_ready:false, mode:'hold'};
  assert.equal(connectionState(active,'this-window').ready,true);
  for (const tool of ['servo','sensor','led','audio','files']) {
    assert.equal(toolState(tool,{...active,link_stale:true},'this-window').tone,'waiting');
    assert.equal(toolState(tool,active,'other-window').label,'Read only');
    assert.equal(toolState(tool,{...active,connected:false,reconnecting:true},'this-window').label,'Reconnecting');
  }
  assert.equal(connectionState({error:'No board'},'this-window').tone,'error');
  assert.equal(connectionState({},'this-window',true).tone,'preview');
  assert.equal(toolState('servo',{},'this-window',true).tone,'preview');
  for (const tool of ['sensor','audio','files']) assert.equal(toolState(tool,{},'this-window',true).label,'Robot connection required');
  assert.equal(toolState('sensor',active,'this-window').label,'Live');
  assert.equal(toolState('files',active,'this-window').label,'No SD card');
  assert.equal(toolState('files',{...active,sd_ready:true},'this-window').label,'Card mounted');
  assert.equal(toolState('audio',{...active,audio:{active:true,error:'Closed'}},'this-window').tone,'error');
  assert.equal(toolState('audio',{...active,audio:{active:true}},'this-window').label,'Live');
  console.log('PASS workspace states: ownership, stale/recovery, preview, SD and audio errors');
})().catch(error=>{console.error(error);process.exitCode=1;});
