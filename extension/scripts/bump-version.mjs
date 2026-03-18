/**
 * Prebuild script: increments patch version in package.json and public/manifest.json.
 * Runs automatically before `npm run build` via the "prebuild" npm lifecycle hook.
 */
import { readFileSync, writeFileSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = resolve(__dirname, '..');

function bumpPatch(filePath) {
  const raw = readFileSync(filePath, 'utf8');
  const obj = JSON.parse(raw);
  const [major, minor, patch] = obj.version.split('.').map(Number);
  obj.version = `${major}.${minor}.${patch + 1}`;
  writeFileSync(filePath, JSON.stringify(obj, null, 2) + '\n');
  return obj.version;
}

const pkgPath = resolve(root, 'package.json');
const manifestPath = resolve(root, 'public/manifest.json');

const newVersion = bumpPatch(pkgPath);
bumpPatch(manifestPath);

console.log(`[bump-version] ${newVersion}`);
