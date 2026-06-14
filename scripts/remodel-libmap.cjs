const fs = require('fs');

const files = ['libmap.js', 'docs/libmap.js'];
const specialRe = /^(?:mailto|tel|javascript|data|blob):/i;
const externalRe = /^(?:[a-z][a-z0-9+.-]*:)?\/\//i;

const stripSlashes = value => String(value || '').replace(/^\/+|\/+$/g, '');
const escapeRe = value => String(value).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const identRe = /^[A-Za-z_$][A-Za-z0-9_$]*$/;
const keyText = key => identRe.test(key) ? key : JSON.stringify(key);

function stringifyConfig(value, indent = 0, key = '') {
  const pad = ' '.repeat(indent);
  const nextPad = ' '.repeat(indent + 2);
  if (Array.isArray(value)) {
    if (!value.length) return '[]';
    if (key === 'items') {
      return '[\n' + value.map(item => nextPad + stringifyInline(item)).join(',\n') + '\n' + pad + ']';
    }
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
  }) && stringifyInline(value).length <= 96;
}

function joinPath(...parts) {
  const raw = parts.filter(value => value != null && String(value) !== '').join('/');
  return raw.replace(/([^:]\/)\/+/g, '$1').replace(/\/+$/, '');
}

function parsePath(path) {
  const raw = String(path || '').trim();
  if (!raw || specialRe.test(raw) || externalRe.test(raw)) return null;
  const clean = raw.replace(/[?#].*$/, '');
  const match = clean.match(/^(.*)\/([^/]+)\/([^/]+)$/);
  if (!match) return null;
  return {
    base: (match[1] + '/').replace(/\/+/g, '/'),
    dir: match[2],
    homeName: match[3],
    clean,
  };
}

function commonBase(paths) {
  if (!paths.length) return '';
  const rows = paths.map(path => stripSlashes(path).split('/').filter(Boolean));
  const parts = [];
  for (let index = 0; ; index++) {
    const value = rows[0][index];
    if (!value || !rows.every(row => row[index] === value)) break;
    parts.push(value);
  }
  return parts.length ? '/' + parts.join('/') + '/' : '';
}

function inferNumericId(item, parsed) {
  if (typeof item.id === 'number') return item.id;
  if (/^\d+$/.test(parsed?.dir || '')) return Number(parsed.dir);
  for (const source of [item.volume, item.label]) {
    const match = String(source || '').match(/(?:^|[^\d])0*(\d{1,3})(?:[^\d]|$)/);
    if (match) return Number(match[1]);
  }
  return null;
}

function formatIdPattern(id) {
  return `0*${escapeRe(id)}`;
}

function detectVolumeFromText(text, id) {
  const label = String(text || '').trim();
  if (!label || id == null) return '';
  const n = formatIdPattern(id);
  const patterns = [
    { re: new RegExp(`^Band\\s+${n}\\b`, 'i'), format: 'Band {id}' },
    { re: new RegExp(`^Volume\\s+${n}\\b`, 'i'), format: 'Volume {id}' },
    { re: new RegExp(`^Vol\\.?\\s+${n}\\b`, 'i'), format: 'Vol. {id}' },
    { re: new RegExp(`^Том\\s+${n}\\b`, 'i'), format: 'Том {id}' },
    { re: new RegExp(`^第\\s*${n}\\s*卷`, 'i'), format: '第{id}卷' },
    { re: new RegExp(`^Werke\\s+${n}\\b`, 'i'), format: 'Werke {id}' },
    { re: new RegExp(`^II/${n}\\b`, 'i'), format: 'II/{id}' },
  ];
  for (const pattern of patterns) {
    const match = label.match(pattern.re);
    if (match) return { volume: match[0].trim(), format: pattern.format };
  }
  return '';
}

function inferVolume(item, id) {
  const fromLabel = detectVolumeFromText(item.label, id);
  if (fromLabel) return fromLabel;
  if (item.volume) {
    const detected = detectVolumeFromText(item.volume, id);
    return { volume: item.volume, format: detected?.format || '' };
  }
  return { volume: '', format: '' };
}

function stripVolumePrefix(label, volume, id) {
  let result = String(label || '').trim();
  if (volume) result = result.replace(new RegExp('^' + escapeRe(volume) + '\\s*[:：]?\\s*', 'i'), '').trim();
  if (id != null) {
    const n = formatIdPattern(id);
    result = result
      .replace(new RegExp(`^Band\\s+${n}\\b\\s*[:：]?\\s*`, 'i'), '')
      .replace(new RegExp(`^Volume\\s+${n}\\b\\s*[:：]?\\s*`, 'i'), '')
      .replace(new RegExp(`^Vol\\.?\\s+${n}\\b\\s*[:：]?\\s*`, 'i'), '')
      .replace(new RegExp(`^Том\\s+${n}\\b\\s*[:：]?\\s*`, 'i'), '')
      .replace(new RegExp(`^第\\s*${n}\\s*卷\\s*[:：]?\\s*`, 'i'), '')
      .replace(new RegExp(`^II/${n}\\b\\s*[:：]?\\s*`, 'i'), '');
  }
  result = result.replace(/^[(（]\s*(.*?)\s*[)）]$/, '$1').trim();
  return result;
}

function resolvedPath(base, item) {
  const name = item.dir ?? item.id;
  if (name == null || name === '') return '';
  if (String(name).startsWith('/')) return joinPath(name, item.homeName || 'index.html');
  if (!base) return item.path || '';
  return joinPath(base, name, item.homeName || 'index.html');
}

function pickGroupBase(col, group) {
  if (group.basePath) return group.basePath;
  const parsed = (group.items || []).map(item => parsePath(item.path)).filter(Boolean);
  if (!parsed.length || parsed.length !== (group.items || []).length) return col.basePath || '';
  const common = commonBase(parsed.map(item => item.base));
  if (common && stripSlashes(common) !== stripSlashes(col.basePath || '')) {
    group.basePath = common;
    return common;
  }
  return col.basePath || '';
}

function chooseVolumeFormat(items) {
  const counts = new Map();
  for (const item of items) {
    const parsed = parsePath(item.path);
    const id = inferNumericId(item, parsed);
    if (id == null) continue;
    const info = inferVolume(item, id);
    if (info.format) counts.set(info.format, (counts.get(info.format) || 0) + 1);
  }
  let best = '', bestCount = 0;
  for (const [format, count] of counts) {
    if (count > bestCount) {
      best = format;
      bestCount = count;
    }
  }
  return bestCount ? best : '';
}

function stripRelativeBase(parsedBase, base) {
  const cleanBase = stripSlashes(base);
  const cleanParsed = stripSlashes(parsedBase);
  if (!cleanBase || cleanParsed === cleanBase) return '';
  return cleanParsed.startsWith(cleanBase + '/') ? cleanParsed.slice(cleanBase.length + 1) : '';
}

function transformItem(item, col, group, base) {
  const parsed = parsePath(item.path);
  if (!parsed) {
    const numericId = inferNumericId(item, null);
    if (numericId == null) return { ...item };
    const info = inferVolume(item, numericId);
    if (!group.volumeFormat && info.format) group.volumeFormat = info.format;
    const generated = group.volumeFormat ? group.volumeFormat.replace(/\{id\}/g, numericId) : '';
    const next = { ...item, id: numericId };
    const label = stripVolumePrefix(item.label, info.volume || generated, numericId);
    if (label) next.label = label;
    else delete next.label;
    if (info.volume && info.volume !== generated && info.format !== group.volumeFormat) next.volume = info.volume;
    else delete next.volume;
    if (next.kind === 'volume') delete next.kind;
    return next;
  }

  const numericId = inferNumericId(item, parsed);
  const isNumericVolume = numericId != null && /^\d+$/.test(parsed.dir);
  const id = isNumericVolume ? numericId : (item.id ?? parsed.dir);
  const next = { id };

  if (!isNumericVolume) next.kind = item.kind || 'book';

  const info = isNumericVolume ? inferVolume(item, numericId) : { volume: item.volume || '', format: '' };
  if (isNumericVolume && !group.volumeFormat && info.format) group.volumeFormat = info.format;
  const generated = group.volumeFormat && isNumericVolume ? group.volumeFormat.replace(/\{id\}/g, numericId) : '';
  if (info.volume && info.volume !== generated && info.format !== group.volumeFormat) next.volume = info.volume;

  const label = stripVolumePrefix(item.label, info.volume || generated, numericId);
  if (label) next.label = label;

  const nested = stripRelativeBase(parsed.base, base);
  const dir = nested ? nested + '/' + parsed.dir : parsed.dir;
  if (dir && String(dir) !== String(id)) next.dir = dir;
  if (parsed.homeName && parsed.homeName !== 'index.html') next.homeName = parsed.homeName;
  if (resolvedPath(base, next).replace(/[?#].*$/, '') !== parsed.clean) next.path = item.path;

  for (const [key, value] of Object.entries(item)) {
    if (!['id', 'kind', 'label', 'path', 'dir', 'homeName', 'volume'].includes(key)) next[key] = value;
  }
  return next;
}

function remodelConfig(config) {
  for (const col of config) {
    if (!col.groups) continue;
    for (const group of col.groups) {
      if (!group.items?.length) continue;
      const base = pickGroupBase(col, group);
      if (!group.volumeFormat) {
        const format = chooseVolumeFormat(group.items);
        if (format) group.volumeFormat = format;
      }
      group.items = group.items.map(item => transformItem(item, col, group, base));
    }
    const formattedGroups = col.groups.filter(group => group.items?.length && group.volumeFormat);
    const counts = new Map();
    for (const group of formattedGroups) counts.set(group.volumeFormat, (counts.get(group.volumeFormat) || 0) + 1);
    let bestFormat = '', bestCount = 0;
    for (const [format, count] of counts) {
      if (count > bestCount) {
        bestFormat = format;
        bestCount = count;
      }
    }
    if (bestFormat && !col.volumeFormat && (bestCount > 1 || formattedGroups.length === 1)) col.volumeFormat = bestFormat;
    if (col.volumeFormat) {
      for (const group of formattedGroups) {
        if (group.volumeFormat === col.volumeFormat) delete group.volumeFormat;
      }
    }
  }
  return config;
}

for (const file of files) {
  const before = fs.readFileSync(file, 'utf8');
  const config = new Function('window', before + '\nreturn window.LIBRARY_CONFIG;')({});
  const afterConfig = remodelConfig(config);
  const after = '// Auto-generated from libmap.js - browser-compatible\nwindow.LIBRARY_CONFIG = ' + stringifyConfig(afterConfig) + ';\n';
  fs.writeFileSync(file, after, 'utf8');
  console.log(`${file}: ${Buffer.byteLength(before)} -> ${Buffer.byteLength(after)}`);
}
