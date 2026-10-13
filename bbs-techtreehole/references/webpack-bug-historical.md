# NodeBB Webpack Composer Bug — Historical Record (2026-05-26 to 2026-05-29)

## Status: RESOLVED in v4.12.0 (2026-05-27)

**GitHub Issue #14296** — Closed after v4.12.0 release.
Fix: commit `16c43a4` — "use hooks to update thumb counts" — refactored topicThumbs.js to use hooks instead of `require(['composer'])`.

## Timeline

- **2026-05-26**: Bug discovered during initial NodeBB v4.11.0 Docker deployment. Webpack ERROR: `Module not found: Error: Can't resolve 'composer'`. All pages return 500.
- **2026-05-26**: Filed GitHub issue #14296. Barisusakli responded: `Is nodebb-plugin-composer active?` and later confirmed hooks approach is the correct fix.
- **2026-05-27**: v4.12.0 released with hooks refactor.
- **2026-05-29**: Upgraded to v4.12.0. Bug is gone.

## Workaround (if stuck on 4.11.x)

Patch webpack.common.js with composer alias:
```js
'composer': path.resolve(__dirname, 'node_modules/nodebb-plugin-composer-default/static/lib/composer'),
```

Then `docker commit nodebb nodebb-patched:4.11.0` and update docker-compose.yml image tag.

## Root Cause

Docker builds copy plugin JS to `build/public/src/modules/`, but webpack common config doesn't alias `'composer'` to the actual path. Non-Docker builds work because the files happen to be in the right place.

## Docker Build Pain

`node nodebb build` always starts a web installer on port 4567, so it conflicts with a running container. The only clean build is during initial container startup (before 4567 is occupied).
