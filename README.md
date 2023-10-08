# Docker MyFinance

Foram feitos três containers:
- O container app-myfin, baseado no Alpine Linux, roda a aplicação python/django (não incluida) com Gunicorn.
- O container mysql-myfin roda o banco de dados MySQL.
- O container nginx-myfin, baseado no Alpine Linux, roda o NginX que cria o proxi reverso e serve a parte estática da aplicação.

## Configurando a aplicação

- Clone o repositorio do myfinance dentro da pasta raiz deste projeto.
- Crie o arquivo o .env com as variáveis de ambiente utilizadas nos containers.
- Configure o arquivo /etc/hosts para que o endereço myfinance.com seja redirecinoado para: 0.0.0.0.
- Na pasta raiz do docker rode o comando:
> docker-compose up

Se todas as configurações estão corretas e os containers subiram corretamente, a aplicação ficará disponível acessando myfinance.com no browser. Baixe os containers apertando Ctrl + C e passe para os próximos passos.

## Configurando o início automático

Para inicializar automaticamente a aplicação com o sistema, copie o arquivo myfinance.service para /etc/systemd/system, recarregue as configurações do systemd, inicie o serviço e habilite sua inicialização automática:

> sudo cp myfinance.service /ets/systemd/system/  
> sudo systemctl daemon-reload  
> sudo systemctl start myfinance.service  
> sudo systemctl enable myfinance.service  