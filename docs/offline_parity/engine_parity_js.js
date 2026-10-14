/* 把 index.html 里的浏览器内置引擎抽出来跑，与 Python 后端结果逐字段比对。
   用法：node docs/offline_parity/engine_parity_js.js
         需要先跑过 engine_parity_py.py 生成 engine_py_out*.json（CASE_FILE 需一致）。 */
const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..', '..');   // 仓库根目录（本文件位于 docs/offline_parity/）
const TMP = __dirname;
const HTML = path.join(ROOT, 'templates', 'index.html');

const html = fs.readFileSync(HTML, 'utf8');
const CASE_FILE = process.env.CASE_FILE || 'engine_cases.json';
const PY_OUT = CASE_FILE.replace('cases', 'py_out');
const startMark = '// ---------- A. Python 兼容随机数';
const endMark = '// ===== 后端地址（API Base）=====';
const i0 = html.indexOf(startMark);
const i1 = html.indexOf(endMark);
if(i0 < 0 || i1 < 0 || i1 <= i0){
  console.error('未能定位引擎代码区间（start=%s end=%s）', i0, i1);
  process.exit(1);
}
const engineJs = html.slice(i0, i1);
console.log('引擎代码长度：%d 字符', engineJs.length);

const ctxStub = new Proxy({}, { get: () => () => {}, set: () => true });
const sandbox = {
  console,
  Math, Number, String, Boolean, Array, Object, JSON, Set, Map, isFinite, parseFloat, parseInt,
  Uint32Array, Promise, Error, Symbol, Date,
  setTimeout, clearTimeout,
  document: { createElement: () => ({ width: 0, height: 0, getContext: () => ctxStub, toDataURL: () => 'data:image/png;base64,STUB' }) },
  window: {}, localStorage: {getItem: () => null, setItem: () => {}, removeItem: () => {}},
  location: {search: ''},
  fetch: () => Promise.reject(new Error('offline')),
  $: () => null,
};
sandbox.globalThis = sandbox;

const cases = JSON.parse(fs.readFileSync(path.join(TMP, CASE_FILE), 'utf8')).cases;
const pyOut = JSON.parse(fs.readFileSync(path.join(TMP, PY_OUT), 'utf8'));
sandbox.__cases = cases;

const harness = `
__results = __cases.map(function(c){
  try{
    var fn = c.kind === 'enhanced' ? jsLocalSimulateEnhanced : jsLocalSimulate;
    var d = fn(c.params);
    delete d.curve;
    return d;
  }catch(e){
    return {__jsError: String((e && e.message) || e)};
  }
});
`;
vm.runInNewContext(engineJs + '\n' + harness, sandbox, {filename: 'engine.js'});
const jsOut = sandbox.__results;

function diff(a, b, p, out){
  if(a === b) return;
  if(a === null || b === null || typeof a !== 'object' || typeof b !== 'object'){
    out.push(p + ': JS=' + JSON.stringify(a) + ' PY=' + JSON.stringify(b));
    return;
  }
  if(Array.isArray(a) !== Array.isArray(b)){ out.push(p + ': 容器类型不同'); return; }
  if(Array.isArray(a)){
    if(a.length !== b.length){ out.push(p + ': 长度 JS=' + a.length + ' PY=' + b.length); return; }
    for(let i = 0; i < a.length; i++) diff(a[i], b[i], p + '[' + i + ']', out);
    return;
  }
  const keys = new Set(Object.keys(a).concat(Object.keys(b)));
  for(const k of keys) diff(a[k], b[k], p + '.' + k, out);
}

let failed = 0;
const METRIC_KEYS = ['metrics', 'grid', 'frames', 'floors', 'passengers', 'unit'];
cases.forEach((c, i) => {
  const a = jsOut[i], b = pyOut[i];
  if(!b){ console.log(`[${i}] ${c.kind} Python 侧无结果`); failed++; return; }
  if(b.error){                              // 后端直接报错（参数非法）
    if(a && a.__jsError){
      console.log(`[${i}] ERR-OK ${c.kind} ${JSON.stringify(c.params)}  两侧一致报错：PY「${b.error}」/ JS「${a.__jsError}」`);
    }else{
      failed++;
      console.log(`[${i}] ERR-DIFF ${c.kind} PY 报错「${b.error}」，但 JS 未报错：${JSON.stringify(a).slice(0, 120)}`);
    }
    return;
  }
  if(a && a.__jsError){ failed++; console.log(`[${i}] ERR-DIFF ${c.kind} JS 报错「${a.__jsError}」，但 PY 正常返回`); return; }
  const out = [];
  for(const key of METRIC_KEYS){
    if(a[key] === undefined && b[key] === undefined) continue;
    diff(a[key], b[key], key, out);
  }
  const tag = c.kind + ' ' + JSON.stringify(c.params);
  if(out.length === 0){
    console.log(`[${i}] OK   ${tag}  →  metrics=${JSON.stringify(a.metrics)}`);
  }else{
    failed++;
    console.log(`[${i}] DIFF ${tag}`);
    out.slice(0, 6).forEach(line => console.log('        ' + line));
    if(out.length > 6) console.log(`        ... 共 ${out.length} 处差异`);
  }
});
console.log(failed === 0
  ? `\n全部 ${cases.length} 组：浏览器内置引擎与 Python 后端逐字段一致 ✅`
  : `\n有 ${failed} / ${cases.length} 组存在差异 ❌`);
