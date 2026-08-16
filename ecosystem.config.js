module.exports = {
  apps: [
    {
      name: "bp-diary-bot",
      script: "bot.py",
      interpreter: ".venv/bin/python",
      cwd: __dirname,
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 5000,
      log_date_format: "YYYY-MM-DD HH:mm:ss",
      error_file: "logs/bot-error.log",
      out_file: "logs/bot-out.log",
      merge_logs: true,
    },
  ],
};
