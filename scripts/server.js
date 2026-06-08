const http = require('http');
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');

// ==================== 配置 ====================
const CONFIG = {
    pyScript: path.join(__dirname, '.', 'search-server.py'),
    pyPort: process.env.PY_PORT ||49107,
    webPort: process.env.PORT || 17117,
    webHost: process.env.HOST || '0.0.0.0',
    staticDir: __dirname,
    apiPrefix: '/api/',
    pyReadyTimeout: 30000,
    pyCheckInterval: 200,
};

const C = {
    g: '\x1b[32m', y: '\x1b[33m', r: '\x1b[31m', c: '\x1b[36m', x: '\x1b[0m'
};
const log = {
    info: (...a) => console.log(`${C.c}[srv]${C.x}`, ...a),
    ok: (...a) => console.log(`${C.g}[srv]${C.x}`, ...a),
    warn: (...a) => console.warn(`${C.y}[srv]${C.x}`, ...a),
    err: (...a) => console.error(`${C.r}[srv]${C.x}`, ...a),
};

function startPython() {
    return new Promise((resolve, reject) => {
        if (!fs.existsSync(CONFIG.pyScript)) {
            return reject(new Error(`Python 脚本不存在: ${CONFIG.pyScript}`));
        }
        log.info('启动 Python 查询服务...', CONFIG.pyScript);
        const py = spawn('python', [CONFIG.pyScript], {
            env: { ...process.env, PORT: String(CONFIG.pyPort) },
            stdio: 'inherit',
        });
        py.on('error', (err) => reject(new Error(`无法启动 Python: ${err.message}`)));
        py.on('exit', (code) => {
            if (code !== null && code !== 0) {
                log.err(`Python 进程异常退出 (code ${code})`);
                process.exit(1);
            }
        });
        const startTime = Date.now();
        const check = () => {
            const sock = require('net').createConnection(CONFIG.pyPort, '127.0.0.1');
            sock.once('connect', () => {
                sock.end();
                log.ok(`Python 查询服务就绪: http://127.0.0.1:${CONFIG.pyPort}`);
                resolve(py);
            });
            sock.once('error', () => {
                if (Date.now() - startTime > CONFIG.pyReadyTimeout) {
                    py.kill();
                    return reject(new Error(`Python 服务 ${CONFIG.pyReadyTimeout}ms 内未就绪`));
                }
                setTimeout(check, CONFIG.pyCheckInterval);
            });
        };
        check();
    });
}

function proxyToPython(req, res) {
    const options = {
        hostname: '127.0.0.1',
        port: CONFIG.pyPort,
        path: req.url,
        method: req.method,
        headers: { ...req.headers, host: `127.0.0.1:${CONFIG.pyPort}` },
    };
    const proxyReq = http.request(options, (proxyRes) => {
        res.writeHead(proxyRes.statusCode, proxyRes.headers);
        proxyRes.pipe(res);
    });
    proxyReq.on('error', (err) => {
        log.err('代理到 Python 失败:', err.message);
        if (!res.headersSent) {
            res.writeHead(502);
            res.end(JSON.stringify({ error: 'Python API unavailable', detail: err.message }));
        }
    });
    req.pipe(proxyReq);
}

const MIME = {
    '.html': 'text/html', '.htm': 'text/html', '.css': 'text/css',
    '.js': 'application/javascript', '.json': 'application/json',
    '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
    '.gif': 'image/gif', '.svg': 'image/svg+xml', '.ico': 'image/x-icon',
    '.woff2': 'font/woff2', '.woff': 'font/woff', '.ttf': 'font/ttf',
    '.db': 'application/octet-stream', '.wasm': 'application/wasm',
};

function serveStatic(req, res) {
    let reqPath = decodeURIComponent(new URL(req.url, `http://localhost`).pathname);
    if (reqPath.endsWith('/')) reqPath += 'index.html';
    const filePath = path.join(CONFIG.staticDir, reqPath);
    const resolved = path.resolve(filePath);
    const rootResolved = path.resolve(CONFIG.staticDir);
    if (!resolved.startsWith(rootResolved + path.sep) && resolved !== rootResolved) {
        res.writeHead(403); res.end('Forbidden'); return;
    }
    const ext = path.extname(resolved).toLowerCase();
    fs.readFile(resolved, (err, data) => {
        if (err) {
            if (err.code === 'ENOENT') {
                const indexPath = path.join(CONFIG.staticDir, 'index.html');
                if (fs.existsSync(indexPath) && reqPath !== '/index.html') {
                    fs.readFile(indexPath, (e2, d2) => {
                        if (e2) { res.writeHead(404); res.end('Not Found'); }
                        else { res.writeHead(200, { 'Content-Type': 'text/html' }); res.end(d2); }
                    });
                    return;
                }
                res.writeHead(404); res.end('Not Found');
            } else {
                res.writeHead(500); res.end('Internal Server Error');
            }
            return;
        }
        res.writeHead(200, {
            'Content-Type': MIME[ext] || 'application/octet-stream',
            'Cache-Control': ext === '.html' ? 'no-cache' : 'public, max-age=3600',
        });
        res.end(data);
    });
}

function startWebServer() {
    const server = http.createServer((req, res) => {
        res.setHeader('Access-Control-Allow-Origin', '*');
        res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
        res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
        if (req.method === 'OPTIONS') { res.writeHead(204); res.end(); return; }
        if (req.url.startsWith(CONFIG.apiPrefix)) {
            proxyToPython(req, res);
        } else {
            serveStatic(req, res);
        }
    });
    server.listen(CONFIG.webPort, CONFIG.webHost, () => {
        log.ok(`静态服务就绪: http://${CONFIG.webHost === '0.0.0.0' ? 'localhost' : CONFIG.webHost}:${CONFIG.webPort}`);
        log.ok(`访问地址: http://localhost:${CONFIG.webPort}/search.html`);
    });
    server.on('error', (err) => {
        if (err.code === 'EADDRINUSE') {
            log.err(`端口 ${CONFIG.webPort} 被占用`); process.exit(1);
        }
        throw err;
    });
    return server;
}

async function main() {
    let pyProcess;
    try {
        pyProcess = await startPython();
        startWebServer();
    } catch (e) {
        log.err('启动失败:', e.message);
        process.exit(1);
    }
    const shutdown = (signal) => {
        log.warn(`收到 ${signal}，正在关闭...`);
        if (pyProcess) pyProcess.kill();
        process.exit(0);
    };
    process.on('SIGINT', () => shutdown('SIGINT'));
    process.on('SIGTERM', () => shutdown('SIGTERM'));
    if (process.platform === 'win32') {
        require('readline').createInterface({ input: process.stdin, output: process.stdout })
            .on('SIGINT', () => shutdown('SIGINT'));
    }
}
main();