import { defineConfig } from 'astro/config';

export default defineConfig({
  site: 'https://www.kayur.ai',
  trailingSlash: 'always',
  build: {
    format: 'directory',
  },
});
