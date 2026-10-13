const fs = require('fs');
const path = require('path');

const webpackConfigPath = '/usr/src/app/webpack.common.js';

if (!fs.existsSync(webpackConfigPath)) {
  console.error('Cannot find webpack.common.js at', webpackConfigPath);
  process.exit(1);
}

let content = fs.readFileSync(webpackConfigPath, 'utf8');

if (content.includes("'composer':")) {
  console.log('Composer alias already present, skipping patch.');
  process.exit(0);
}

// Insert composer alias after the jquery-ui/widgets line
// Using a robust regex-free string replacement
const target = "'jquery-ui/widgets': path.resolve(__dirname, 'node_modules/jquery-ui/ui/widgets'),";
const insertion = target + "\n      'composer': path.resolve(__dirname, 'node_modules/nodebb-plugin-composer-default/static/lib/composer'),";

if (!content.includes(target)) {
  console.error('Could not find insertion point:', target);
  process.exit(1);
}

content = content.replace(target, insertion);
fs.writeFileSync(webpackConfigPath, content, 'utf8');
console.log('Composer alias patch applied successfully.');