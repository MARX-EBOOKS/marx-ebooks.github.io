const fs = require('fs');

const files = ['libmap.js', 'docs/libmap.js'];
const identRe = /^[A-Za-z_$][A-Za-z0-9_$]*$/;
const keyText = key => identRe.test(key) ? key : JSON.stringify(key);
const externalRe = /^(?:[a-z][a-z0-9+.-]*:)?\/\//i;
const specialRe = /^(?:mailto|tel|javascript|data|blob):/i;

function stringifyConfig(value, indent = 0, key = '') {
  const pad = ' '.repeat(indent);
  const nextPad = ' '.repeat(indent + 2);
  if (Array.isArray(value)) {
    if (!value.length) return '[]';
    if (key === 'items') return '[\n' + value.map(item => nextPad + stringifyInline(item)).join(',\n') + '\n' + pad + ']';
    if (value.every(item => item == null || typeof item !== 'object')) return '[' + value.map(stringifyInline).join(', ') + ']';
    return '[\n' + value.map(item => nextPad + stringifyConfig(item, indent + 2)).join(',\n') + '\n' + pad + ']';
  }
  if (value && typeof value === 'object') {
    const entries = Object.entries(value);
    if (!entries.length) return '{}';
    if (isShortObject(value)) return stringifyInline(value);
    return '{\n' + entries.map(([entryKey, entryValue]) => {
      return nextPad + keyText(entryKey) + ': ' + stringifyConfig(entryValue, indent + 2, entryKey);
    }).join(',\n') + '\n' + pad + '}';
  }
  return JSON.stringify(value);
}

function stringifyInline(value) {
  if (Array.isArray(value)) return '[' + value.map(stringifyInline).join(', ') + ']';
  if (value && typeof value === 'object') {
    const body = Object.entries(value).map(([entryKey, entryValue]) => {
      return keyText(entryKey) + ': ' + stringifyInline(entryValue);
    }).join(', ');
    return body ? '{ ' + body + ' }' : '{}';
  }
  return JSON.stringify(value);
}

function isShortObject(value) {
  const entries = Object.entries(value);
  if (!entries.length || entries.length > 4) return false;
  return entries.every(([, entryValue]) => {
    if (entryValue == null) return true;
    if (Array.isArray(entryValue)) return entryValue.every(item => item == null || typeof item !== 'object');
    return typeof entryValue !== 'object';
  }) && stringifyInline(value).length <= 112;
}

function joinPath(...parts) {
  const raw = parts.filter(value => value != null && String(value) !== '').join('/');
  return raw.replace(/([^:]\/)\/+/g, '$1');
}

function cleanDocPath(value) {
  const raw = String(value || '').trim();
  if (!raw || specialRe.test(raw) || externalRe.test(raw)) return '';
  const clean = raw.replace(/[?#].*$/, '');
  return clean.startsWith('/') ? clean : '/' + clean;
}

function docPathFor(col, group, item) {
  const raw = cleanDocPath(item?.path);
  if (raw) return raw;
  const name = item?.dir ?? item?.id;
  if (name == null || name === '') return '';
  const home = item?.homeName || 'index.html';
  if (String(name).startsWith('/')) return cleanDocPath(joinPath(name, home));
  const base = group?.basePath || col?.basePath || '';
  return cleanDocPath(joinPath(base, name, home));
}

function homeDirFor(docPath) {
  const clean = cleanDocPath(docPath);
  if (!clean) return '';
  const dir = clean.replace(/\/[^/]*$/, '/');
  return dir.endsWith('/') ? dir : dir + '/';
}

function homeNameFor(docPath) {
  return cleanDocPath(docPath).split('/').pop() || 'index.html';
}

function volumeFor(col, group, item) {
  if (item?.volume) return String(item.volume);
  if (typeof item?.id !== 'number') return '';
  const format = group?.volumeFormat || col?.volumeFormat || '';
  return format ? format.replace(/\{id\}/g, item.id) : '';
}

function fullLabel(item, volume) {
  const label = String(item?.label || item?.title || '').trim();
  if (!volume) return label || String(item?.id ?? '');
  if (!label || label === volume || label.startsWith(volume)) return label || volume;
  return volume + (/^[\s(:：,，.;；]/.test(label) ? ' ' : ': ') + label;
}

function orderedItem(item, col, group) {
  const docPath = docPathFor(col, group, item);
  const dir = homeDirFor(docPath);
  const homeName = homeNameFor(docPath);
  const volume = volumeFor(col, group, item);
  const next = {};

  if (item.id != null) next.id = item.id;
  if (item.kind) next.kind = item.kind;
  const label = fullLabel(item, volume);
  if (label) next.label = label;
  if (volume) next.volume = volume;
  if (dir) next.dir = dir;
  if (homeName && homeName !== 'index.html') next.homeName = homeName;

  for (const [key, value] of Object.entries(item)) {
    if (['id', 'kind', 'label', 'title', 'volume', 'path', 'dir', 'homeName'].includes(key)) continue;
    next[key] = value;
  }
  return next;
}

function stripVolumeFormat(object) {
  const { volumeFormat, ...rest } = object;
  return rest;
}

function remodelConfig(config) {
  return (config || []).map(col => {
    const nextCol = stripVolumeFormat({ ...col });
    if (!Array.isArray(col.groups)) return nextCol;
    nextCol.groups = col.groups.map(group => {
      const nextGroup = stripVolumeFormat({ ...group });
      if (Array.isArray(group.items)) {
        nextGroup.items = group.items.map(item => orderedItem(item, col, group));
      }
      return nextGroup;
    });
    return nextCol;
  });
}

for (const file of files) {
  const before = fs.readFileSync(file, 'utf8');
  const config = new Function('window', before + '\nreturn window.LIBRARY_CONFIG;')({});
  const afterConfig = remodelConfig(config);
  const after = '// Auto-generated from libmap.js - browser-compatible\nwindow.LIBRARY_CONFIG = ' + stringifyConfig(afterConfig) + ';\n';
  fs.writeFileSync(file, after, 'utf8');
  console.log(`${file}: ${Buffer.byteLength(before)} -> ${Buffer.byteLength(after)}`);
}
