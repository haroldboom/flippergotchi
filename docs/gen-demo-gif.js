// Render an animated Flipper One mock-up: a stylised chassis (CSS, original art
// — the docs ship no device image) wrapping the exact 256x144 orange LCD, cycling
// through the catch sequence. Frames -> PNGs; Pillow stitches the GIF.
const { chromium } = require('playwright');
const fs = require('fs');

const OUT = '/root/flippergotchi/docs/_frames';
fs.mkdirSync(OUT, { recursive: true });
const esc = s => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

const FACES = {
  happy: "   .----.\n  ( ^  ^ )\n   )  ww  (\n  ( '--' )~\n   '----'",
  excited: "  *.----.*\n  ( O  O )\n   )  WW  (\n  ( '--' )~\n   '----' !!",
};
const SCENES = {
  popup: " A wild Crypterion appeared!\n NETGEAR  Lv8  [wpa2]\n\n   [A] CAPTURE      [B] RUN",
  aim: "  .--.             ( ~ ~ )\n ( oo )===O        (Crypterion)\n  '--'             ( ~ ~ )\n takes aim with the net-gun...",
  fire: "  .--.   o O o     ( ~ ~ )\n ( oo )-- * * ---> (Crypterion)\n  '--'             ( ~ ~ )\n *fwoomp* -- net away!",
  net: "  .--.           #=[   ]=#\n ( ^^ )          #(Crypterion)#\n  '--'           #=[   ]=#\n ...will it hold?",
  gotcha: " \\(^o^)/         [#######]\n                [Crypterion]  GOTCHA!\n                [#######]\n handshake netted -> bestiary!",
};

function bar(pct) {
  return `<span class="bar" style="width:${Math.round(pct * 1.6)}px"></span>`;
}
function faceScreen(header, face, say) {
  return `<div class="hdr">${esc(header)}</div>
    <pre class="face">${esc(face)}</pre>
    <div class="row">food ${bar(78)}</div>
    <div class="row">enrg ${bar(64)}</div>
    <div class="say">${esc(say)}</div>`;
}
function sceneScreen(say, pre) {
  return `<pre class="big">${esc(pre)}</pre><div class="say">${esc(say)}</div>`;
}

const CSS = `
  *{box-sizing:border-box} body{margin:0;background:#0d0d0f;}
  .device{width:880px;padding:26px 30px 22px;border-radius:46px;
    background:linear-gradient(160deg,#ff8a1e,#f4760b 60%,#d9620a);
    box-shadow:inset 0 2px 6px rgba(255,255,255,.35),0 14px 40px rgba(0,0,0,.5);}
  .brand{font:700 15px/1 monospace;letter-spacing:3px;color:#3a1c02;
    text-align:right;margin-bottom:12px;opacity:.8;}
  .bezel{background:#141414;border-radius:18px;padding:16px;
    box-shadow:inset 0 0 0 2px #000,inset 0 0 14px rgba(0,0,0,.8);}
  .screen{width:520px;height:292px;margin:0 auto;background:#ff8c12;color:#161008;
    font-family:'DejaVu Sans Mono',monospace;padding:14px 16px;border-radius:4px;
    box-shadow:inset 0 0 18px rgba(120,60,0,.55);}
  .hdr{font:700 15px/1.2 monospace;}
  .face{font:15px/15px monospace;white-space:pre;margin:6px 0;}
  .big{font:15px/17px monospace;white-space:pre;margin:18px 0 0;}
  .row{font:13px/1.5 monospace;}
  .bar{display:inline-block;height:8px;background:#161008;vertical-align:middle;}
  .say{font:italic 13px/1.3 monospace;margin-top:10px;}
  .controls{display:flex;align-items:center;justify-content:space-between;
    padding:20px 24px 4px;}
  .dpad{position:relative;width:96px;height:96px;}
  .dpad div{position:absolute;background:#2a2a2a;border-radius:6px;
    box-shadow:0 2px 3px rgba(0,0,0,.5);}
  .dpad .h{top:34px;left:6px;width:84px;height:28px;}
  .dpad .v{top:6px;left:34px;width:28px;height:84px;}
  .dpad .c{top:34px;left:34px;width:28px;height:28px;background:#3a3a3a;
    border-radius:50%;z-index:2;}
  .abtns{display:flex;gap:20px;}
  .abtns b{width:54px;height:54px;border-radius:50%;display:grid;place-items:center;
    font:700 18px/1 monospace;color:#3a1c02;background:#ffd089;
    box-shadow:0 3px 4px rgba(0,0,0,.4),inset 0 2px 3px rgba(255,255,255,.6);}
`;
function chassis(screenHTML) {
  return `<!doctype html><html><head><meta charset="utf-8"><style>${CSS}</style></head>
  <body><div class="device">
    <div class="brand">FLIPPER ONE</div>
    <div class="bezel"><div class="screen">${screenHTML}</div></div>
    <div class="controls">
      <div class="dpad"><div class="h"></div><div class="v"></div><div class="c"></div></div>
      <div class="abtns"><b>B</b><b>A</b></div>
    </div>
  </div></body></html>`;
}

const frames = [
  { ms: 950, html: faceScreen('Flippy Lv.9 juvenile', FACES.happy, 'Flippy: "Best day ever! (^_^)"') },
  { ms: 1150, html: sceneScreen('Flippy: "Ooh, a wild one!"', SCENES.popup) },
  { ms: 520, html: sceneScreen('', SCENES.aim) },
  { ms: 520, html: sceneScreen('', SCENES.fire) },
  { ms: 560, html: sceneScreen('', SCENES.net) },
  { ms: 950, html: sceneScreen('Flippy: "Gotcha!"', SCENES.gotcha) },
  { ms: 1150, html: faceScreen('Flippy Lv.9 juvenile', FACES.excited, 'Flippy: "Caught Crypterion! (^o^)"') },
];

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ deviceScaleFactor: 2 });
  const meta = [];
  for (let i = 0; i < frames.length; i++) {
    await page.setContent(chassis(frames[i].html));
    const el = await page.$('.device');
    const file = `${OUT}/f${String(i).padStart(2, '0')}.png`;
    await el.screenshot({ path: file });
    meta.push({ file, ms: frames[i].ms });
    console.log('frame', i);
  }
  fs.writeFileSync(`${OUT}/frames.json`, JSON.stringify(meta));
  await browser.close();
})();
