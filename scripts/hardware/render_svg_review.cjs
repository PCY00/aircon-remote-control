// CAD SVG raster preview only; preserves the editable vector source.
// sharp comes from SHARP_MODULE (path of an installed sharp package) or from the usual
// Node resolution (a node_modules folder next to this script or on NODE_PATH).
let sharp;
try {
  sharp = require(process.env.SHARP_MODULE || 'sharp');
} catch (error) {
  console.error('sharp not found: install it (npm install sharp) or set SHARP_MODULE to its folder. ' + error.message);
  process.exit(2);
}
const [input, output, width = '2400'] = process.argv.slice(2);
sharp(input, { density: 180 }).resize({width: Number(width)}).flatten({background:'#ffffff'}).png().toFile(output).then(()=>console.log(output));
