const net = require('net');
const websocket = require('ws');

const mr_host = '127.0.0.1';
const mr_port = 1337;

const DEFAULT_WS_PORT = 1338;
const ws_port = parseInt(process.argv[2]) || DEFAULT_WS_PORT;
const ws_host = '127.0.0.1';

console.log(`Listening on port ${ws_port}.`);
const wss = new websocket.Server({ port: ws_port, host: ws_host });
wss.on('connection', ws => {
    console.log(`WS client connected.`)
    const socket = net.createConnection(mr_port, mr_host);

    socket.on('connect', () => {
        console.log('Connected to server.');
    });

    socket.on('data', data => {
        ws.send(data);
    });

    socket.on('close', () => {
        console.log('Connection to server lost.');
        ws.close();
    });

    ws.on('message', data => {
        socket.write(data);
    });
    ws.on('close', () => {
        console.log('WS client disconnected.');
        socket.end();
    });
});
