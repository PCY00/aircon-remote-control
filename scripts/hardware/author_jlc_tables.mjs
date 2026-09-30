// Machine-readable JLC CSVs authored as typed artifact-tool tables, then
// serialized with RFC4180 quoting. No decorative header rows enter the files.
import fs from 'node:fs/promises';
import path from 'node:path';
import assert from 'node:assert/strict';
import { Workbook } from '@oai/artifact-tool';

const folder=path.resolve(process.argv[2]);
const input=JSON.parse(await fs.readFile(path.join(folder,'assembly-tables.json'),'utf8'));
const wb=Workbook.create();
const snapshots=[];
for(const t of input.tables){
  const sheet=wb.worksheets.add(t.sheet);
  const rows=[t.headers,...t.rows.map(row=>t.headers.map(h=>row[h]??''))];
  const range=sheet.getRangeByIndexes(0,0,rows.length,t.headers.length);
  range.values=rows;
  range.setNumberFormat('@');
  assert.deepEqual(range.values,rows,`${t.sheet} must preserve all part identifiers/coordinates`);
  const quote=x=>'"'+String(x??'').replaceAll('"','""')+'"';
  const csv=range.values.map(row=>row.map(quote).join(',')).join('\r\n')+'\r\n';
  await fs.writeFile(path.join(folder,t.file),csv,'utf8');
  const roundTrip=await Workbook.fromCSV(csv,{sheetName:'check'});
  assert.deepEqual(roundTrip.worksheets.getItemAt(0).getUsedRange().values,rows,`${t.file} round trip`);
  range.format.font={name:'Arial',size:11,color:'#1F2937'};
  range.format.rowHeightPx=26;
  sheet.getRangeByIndexes(0,0,1,t.headers.length).format.fill='#17324D';
  sheet.getRangeByIndexes(0,0,1,t.headers.length).format.font={bold:true,color:'#FFFFFF'};
  sheet.getRangeByIndexes(0,0,1,t.headers.length).format.rowHeightPx=38;
  range.format.columnWidthPx=140;
  if(t.sheet==='BOM'){
    sheet.getRange('A:A').format.columnWidthPx=265;
    sheet.getRange('B:B').format.columnWidthPx=205;
    sheet.getRange('C:C').format.columnWidthPx=355;
  }
  if(t.sheet==='Review'){
    sheet.getRange('B:B').format.columnWidthPx=265;
    sheet.getRange('E:E').format.columnWidthPx=490;
    sheet.getRange('N:O').format.columnWidthPx=340;
    sheet.getRange('P:Q').format.columnWidthPx=800;
  }
  sheet.showGridLines=false;
  snapshots.push({file:t.file,rows:rows.length-1,columns:t.headers.length,roundTrip:true});
  const preview=await wb.render({sheetName:t.sheet,autoCrop:'all',scale:1,format:'png'});
  await fs.writeFile(path.join(folder,`preview-${t.sheet.toLowerCase()}.png`),new Uint8Array(await preview.arrayBuffer()));
}
const inspection=await wb.inspect({kind:'workbook,sheet,table',maxChars:3000,tableMaxRows:3,tableMaxCols:5});
await fs.writeFile(path.join(folder,'table-validation.json'),JSON.stringify({tables:snapshots,inspection},null,2));
console.log(JSON.stringify(snapshots));
console.log('TABLE_BUILD_VALIDATION_COMPLETED', {exitCode:process.exitCode ?? 0});
// Rendering workers can change the runtime's shutdown status after completion.
// All writes/renders/inspections and round-trip assertions above were awaited;
// terminate this CLI explicitly only after they succeed (exceptions never reach here).
process.exit(0);
