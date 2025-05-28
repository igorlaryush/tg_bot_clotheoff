gcloud login 
tuna http 5000
then copy url to env

gcloud builds submit . ^
    --tag europe-west4-docker.pkg.dev/tg-bot-clotheoff-prod/bot-repo/telegram-bot:latest ^
    --project=tg-bot-clotheoff-prod

gcloud builds submit . `
    --tag europe-west4-docker.pkg.dev/tg-bot-clotheoff-prod/bot-repo/telegram-bot:latest `
    --project=tg-bot-clotheoff-prod
