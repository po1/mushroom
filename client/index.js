const net = require('net');
const websocket = require('ws');

const mr_host = '127.0.0.1';
const mr_port = 1337;

const ws_host = '127.0.0.1';
const ws_port = 1338;

const wss = new websocket.Server({port: ws_port, host: ws_host});
wss.on('connection', ws => {
    const socket = net.createConnection(mr_port, mr_host);

    socket.on('data', data => {
        ws.send(data);
    });

    socket.on('close', () => {
        ws.close();
    });

    ws.on('message', data => {
        socket.write(data);
    });
    ws.on('close', () => {
        socket.end();
    });
});
