/// <reference types="vitest" />
import { defineConfig } from 'vite';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import react from '@vitejs/plugin-react';
import path from 'node:path';
import type { Plugin } from 'vite';

function frontendSourceFiles(frontendRoot: string): string[] {
  const files: string[] = [
    'index.html',
    'package.json',
    'package-lock.json',
    'tsconfig.json',
    'vite.config.ts',
  ];
  const collect = (relativeRoot: string) => {
    const absoluteRoot = path.join(frontendRoot, relativeRoot);
    if (!fs.existsSync(absoluteRoot)) return;
    const visit = (current: string) => {
      for (const entry of fs.readdirSync(current, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
        const absolute = path.join(current, entry.name);
        if (entry.isDirectory()) visit(absolute);
        else if (entry.isFile()) files.push(path.relative(frontendRoot, absolute).split(path.sep).join('/'));
      }
    };
    visit(absoluteRoot);
  };
  collect('src');
  collect('public');
  return [...new Set(files)].sort();
}

function frontendSourceDigest(frontendRoot: string): string {
  const digest = createHash('sha256');
  for (const relative of frontendSourceFiles(frontendRoot)) {
    digest.update(relative, 'utf8');
    digest.update('\0', 'utf8');
    digest.update(fs.readFileSync(path.join(frontendRoot, relative)));
    digest.update('\0', 'utf8');
  }
  return digest.digest('hex');
}

function outputBytes(output: { type: string; source?: string | Uint8Array; code?: string }): Buffer {
  if (output.type === 'asset') {
    return Buffer.isBuffer(output.source) ? output.source : Buffer.from(output.source ?? '');
  }
  return Buffer.from(output.code ?? '');
}

function outputDigest(output: { type: string; source?: string | Uint8Array; code?: string }): string {
  return createHash('sha256').update(outputBytes(output)).digest('hex');
}

function outputSetDigest(entries: Array<{ path: string; sha256: string }>): string {
  const digest = createHash('sha256');
  for (const entry of entries) {
    digest.update(entry.path, 'utf8');
    digest.update('\0', 'utf8');
    digest.update(entry.sha256, 'utf8');
    digest.update('\0', 'utf8');
  }
  return digest.digest('hex');
}

function frontendBuildIdentityPlugin(frontendRoot: string): Plugin {
  return {
    name: 'dr-frontend-build-identity',
    generateBundle(_options, bundle) {
      const sourceCommit = execFileSync('git', ['rev-parse', 'HEAD'], {
        cwd: path.resolve(frontendRoot, '..'),
        encoding: 'utf8',
      }).trim();
      const sourceDigest = frontendSourceDigest(frontendRoot);
      const outputFiles = Object.entries(bundle)
        .filter(([fileName]) => fileName !== 'build-identity.json')
        .map(([fileName, output]) => ({ path: fileName, sha256: outputDigest(output) }))
        .sort((a, b) => a.path.localeCompare(b.path));
      const indexHtml = path.resolve(frontendRoot, 'index.html');
      if (fs.existsSync(indexHtml)) {
        outputFiles.push({
          path: 'index.html',
          sha256: createHash('sha256').update(fs.readFileSync(indexHtml)).digest('hex'),
        });
        outputFiles.sort((a, b) => a.path.localeCompare(b.path));
      }
      this.emitFile({
        type: 'asset',
        fileName: 'build-identity.json',
        source: `${JSON.stringify({
          schema_version: 'frontend-build-identity.v1',
          source_commit: sourceCommit,
          source_digest: sourceDigest,
          output_files: outputFiles,
          output_set_sha256: outputSetDigest(outputFiles),
        }, null, 2)}\n`,
      });
    },
  };
}

const frontendRoot = __dirname;

export default defineConfig({
  base: '/app/',
  plugins: [react(), frontendBuildIdentityPlugin(frontendRoot)],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, 'src'),
    },
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      '/v1': {
        target: 'http://127.0.0.1:8000',
        // Keep the browser origin visible to the API's same-origin guard.
        changeOrigin: false,
      },
      '/ui': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
      '/health': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  build: {
    outDir: 'dist',
    assetsDir: 'assets',
    sourcemap: true,
    target: 'es2020',
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['tests/**/*.test.{ts,tsx}'],
    css: false,
    fileParallelism: false,
    maxWorkers: 1,
    minWorkers: 1,
    // Chakra/jsdom integration tests can exceed Vitest's 5s default when the
    // full suite is running in parallel on slower local or CI workers.
    testTimeout: 15_000,
  },
});
