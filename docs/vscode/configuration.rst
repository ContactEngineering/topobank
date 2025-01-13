Docker Remote Debugging for VSCode
=======================

To connect to python remote interpreter inside docker, you have to make sure first, that VSCode is aware of your docker.


First you need to ensure SETTINGS.DEBUG = True .
When building the app in docker using docker compose, run the following command to expose the port 5678
```
docker compose -f docker-compose.yml -f docker-compose.debug.yml up -d
```

Once docker django app is up and running need to run the VSCode to attach to the port. Used the below configuration to launch the process.

Configure Remote Python Interpreter
-----------------------------------
Ensure the .vscode/launch.json file has this configuration:

```
{
    "configurations": [
        {
            "name": "Attach: Django Docker",
            "type": "debugpy",
            "request": "attach",
            "connect": {
                "host": "localhost",
                "port": 5678
              },
            "pathMappings": [
                {
                  "localRoot": "${workspaceFolder}/",
                  "remoteRoot": "/development-stack"
                }
              ],
        },
    ]
}
```

Click on side VSCode menu Run and Debug and then click Attach: Django Docker

.. image:: images/1.png

You should be able to now to add breakpoints within the django main app. 


Known issues
------------
* Celery app debugging in VSCode do not work yet.
* VSCode debug will automatically disconnect if django server restarts due to code changes. You must manually re-launch the debugger from VSCode each time.