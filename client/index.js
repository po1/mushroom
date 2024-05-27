const net = require('net');
const websocket = require('ws');

const mr_host = process.env.MUSHROOMD_HOST || '127.0.0.1';
const mr_port = parseInt(process.env.MUSHROOMD_PORT) || 1337;

const DEFAULT_WS_PORT = 1338;
const ws_port = parseInt(process.argv[2]) || DEFAULT_WS_PORT;
const ws_host = undefined;  // listen on all interfaces

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

process.on('SIGINT', function() {
  console.log( "\nGracefully shutting down from SIGINT (Ctrl-C)" );
  // some other closing procedures go here
  process.exit(0);
});
