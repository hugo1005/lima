Notes:

Updates to these configs are ignored now (to allow using different versions at different machines):
git update-index --skip-worktree configs/backend_config.json
git update-index --skip-worktree configs/backend_config_btc_gbp.json

Stop updates on GitHub for markets.db:
git update-index --skip-worktree datasets/markets.db