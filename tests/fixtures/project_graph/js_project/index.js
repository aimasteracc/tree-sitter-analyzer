// index.js - main entry point
const { helper } = require('./src/utils');
const User = require('./src/models/user');
import { format } from './src/formatter';
import config from './src/config.json';

module.exports = { helper, User, format, config };
