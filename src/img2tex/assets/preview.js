"use strict";
let bridge;
const math = document.getElementById('math');
const send = value => bridge.message(JSON.stringify(value));
window.renderFormula = async function(source, id) {
  try {
    katex.render(source, math, {displayMode:true, throwOnError:true, trust:false,
      strict:'error', maxExpand:1000, output:'htmlAndMathml'});
    await document.fonts.ready;
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    send({kind:'render', id:id});
  } catch (error) {
    math.textContent = '预览失败，请检查 LaTeX';
    send({kind:'render', id:id, error:String(error.message || error)});
  }
};
window.formulaBounds = function(exporting) {
  document.body.classList.toggle('exporting', exporting);
  const rect = math.getBoundingClientRect();
  return {x:rect.x, y:rect.y, width:rect.width, height:rect.height};
};
window.exportSvg = async function(source, id) {
  try {
    await MathJax.startup.promise;
    const node = await MathJax.tex2svgPromise(source, {display:true});
    if (node.querySelector('merror, [data-mml-node="merror"]')) {
      throw new Error('SVG 无法转换此 LaTeX，请检查语法或使用 LaTeX 复制');
    }
    const svg = node.querySelector('svg');
    if (svg.querySelector('a, image, script, foreignObject') ||
        Array.from(svg.querySelectorAll('*')).some(element =>
          Array.from(element.attributes).some(attribute =>
            /^on/i.test(attribute.name) || /url\s*\(/i.test(attribute.value) ||
            (/href$/i.test(attribute.name) && !attribute.value.startsWith('#'))))) {
      throw new Error('SVG 仅支持静态公式，不支持链接、图片或外部资源');
    }
    svg.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
    svg.setAttribute('style', 'color:#172034');
    send({kind:'svg', id:id, svg:new XMLSerializer().serializeToString(svg)});
  } catch (error) {
    send({kind:'svg', id:id, error:String(error.message || error)});
  }
};
new QWebChannel(qt.webChannelTransport, channel => {
  bridge = channel.objects.bridge;
  send({kind:'ready'});
});
