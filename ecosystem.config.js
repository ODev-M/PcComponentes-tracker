// Optional PM2 config. systemd (deploy/pccomponentes-tracker.service) is the
// primary way to run this in production — PM2 is provided for convenience.
module.exports = {
    apps: [
        {
            name: 'pccomponentes-tracker',
            script: 'run.py',
            interpreter: './venv/bin/python',
            cwd: __dirname,
            env: {
                PYTHONUNBUFFERED: '1',
            },
            autorestart: true,
            watch: false,
            max_memory_restart: '300M',
            out_file: './logs/out.log',
            error_file: './logs/err.log',
            time: true,
        },
    ],
};
