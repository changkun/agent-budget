// Bundles the client script and copies the stylesheet into dist/.
import { build } from 'esbuild';
import { copyFileSync, mkdirSync } from 'node:fs';

mkdirSync('dist', { recursive: true });
await build({
  entryPoints: ['src/client/main.js'],
  bundle: true,
  minify: true,
  format: 'iife',
  target: 'es2020',
  outfile: 'dist/app.js',
  logLevel: 'warning',
});
copyFileSync('src/client/styles.css', 'dist/styles.css');
console.log('built dist/app.js and dist/styles.css');
