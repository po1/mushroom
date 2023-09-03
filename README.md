MUSHRoom
-- 0.3 "cep"

MUSHRoom is a tool to create and host a MUSH.
You will need python3 to launch the server.

A MUSH is a text-mode game, the server will be reachable by telnet, netcat,
and other very simple TCP/IP text clients. The default port is 1337.
You can change it in a `config.toml` file.

Launching the server:
--------------------

```
pip install .
mushroomd
```


Connecting to the game:
----------------------

```
nc hostname 1337
```

You can also launch the websocket proxy and use the HTML client:
```
cd client && node index.js
```
Then point your browser to `client/index.html`, click connect. Enjoy.


Contributing
============

Send PRs!
Since I'm mostly alone developing this, there's no real roadmap / design doc. Open issues for bugs / feature requests.


Changelog
=========

0.3.0 (2023-09-03)
------------------
* Command refactor
* More power(s)
* Refactors, more refactors
* Now a nice packageable... package
* A tiny bit of onboarding: global config, god player...
* Shiny new HTML client!
* Contributors: Paul

0.2.0 (2014-11-29)
------------------
* Port to python3
* Split in-game API ("FW") in different modules
* Add powers to players
* Layered command resolution (player, room, global)
* Add custom commands to objects, and save them in the DB
* Many fixes
* Contributors: Paul M, Guiniol

0.1.0 (2011-07-06)
------------------
* Initial release
* Architecture draft, objects, commands
* Load/save of the database
* Contributors: Paul M
