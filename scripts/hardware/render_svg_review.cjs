// CAD SVG raster preview only; preserves the editable vector source.
const sharp = require('C:/Users/kksp1/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/sharp');
const [input, output, width = '2400'] = process.argv.slice(2);
sharp(input, { density: 180 }).resize({width: Number(width)}).flatten({background:'#ffffff'}).png().toFile(output).then(()=>console.log(output));
