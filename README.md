# Docker MyFinance

## HTTPS na VM da rede local

O ambiente existente usa o Nginx do projeto `reverse_proxy` para terminar o TLS,
com acesso por `https://myfinance.com` e `https://192.168.100.10`.
O guia de certificados, instalação no Pop!_OS/Android, implantação no Alpine e
renovação está em [`../reverse_proxy/README.md`](../reverse_proxy/README.md).
Atualize também o código do MyFinance antes de habilitar as opções abaixo.

Crie a rede compartilhada antes de iniciar o Compose existente:

```bash
docker network inspect myfinance-proxy >/dev/null 2>&1 || docker network create --subnet 172.30.0.0/24 myfinance-proxy
```

Para ativar o reconhecimento de HTTPS e os cookies seguros, acrescente ao `.env`:

```dotenv
MYFIN_TRUST_HTTPS_PROXY=true
MYFIN_SESSION_COOKIE_SECURE=true
MYFIN_CSRF_COOKIE_SECURE=true
```

Essas opções têm padrão `false`, preservando HTTP enquanto o HTTPS não estiver
instalado. Mantenha hosts e origens existentes, incluindo os dois endereços HTTPS.
O debug não é alterado por esta configuração. O proxy externo deve sobrescrever
`X-Forwarded-Proto`; o Nginx interno preserva esse protocolo até o Django.
A porta 81 agora é publicada somente em `127.0.0.1` da VM; o proxy externo acessa
`nginx-myfin:80` pela rede `myfinance-proxy`. O Compose de desenvolvimento
continua independente e não usa essa rede nem os certificados.

## Segurança de rede e build (S12/S13)

No Compose principal, MySQL (`127.0.0.1:3306`) e Transaction Classifier
(`127.0.0.1:8112`) ficam acessíveis somente pelo loopback do host. Para acesso
administrativo remoto, use um túnel SSH. O Redis não publica porta no host.
Entre containers, os endereços continuam `mysql-myfin:3306`, `redis-myfin:6379`
e `transaction-classifier:8112`; a comunicação interna não depende de portas
publicadas. Essas alterações passam a valer após a recriação dos serviços.

O `.dockerignore` principal usa uma lista de código permitido e exclui arquivos
`.env*`, credenciais, mídia, logs, bancos, exportações e artefatos de treinamento.
O build do classificador usa o `.dockerignore` do próprio repositório
`transaction_classifier`; atualize também esse checkout antes de reconstruir.
O `Dockerfile.dev.dockerignore` permanece exclusivo do build de desenvolvimento.

Variáveis de ambiente precisam ser fornecidas em runtime pelo Compose. Arquivos
`.env` dentro do código não são copiados para a imagem. Para Pluggy, preencha no
`.env` usado pelo Compose (ou no ambiente do processo Compose):

```dotenv
PLUGGY_CLIENT_ID=
PLUGGY_CLIENT_SECRET=
PLUGGY_ITEM_ID=
```

O arquivo de ambiente do Compose não entra na imagem; essas três variáveis são
encaminhadas explicitamente ao Django. Os demais parâmetros continuam usando os
mapeamentos existentes em `environment`. Não grave credenciais no Dockerfile.

Para habilitar o login com Google, preencha no `.env` do Compose:

```dotenv
SOCIAL_LOGIN_ENABLED=true
GOOGLE_OAUTH2_KEY=
GOOGLE_OAUTH2_SECRET=
```

Essas variáveis são encaminhadas pelo bloco compartilhado `environment` aos
serviços Django, incluindo os slots `blue` e `green`. O `.env` do Compose serve
para interpolar os valores; declarar uma variável nele não a adiciona
automaticamente ao container. Atualize este Compose no servidor e recrie o
serviço ativo pelo fluxo habitual de deploy (`mfupdate`). Apenas `restart` não
atualiza o ambiente de um container existente. A opção pessoal de login social
no perfil também deve estar ativada.

Mídia, logs, dados MySQL e modelos existentes continuam nos volumes/bind mounts.
Excluir dados do build não os remove do disco nem substitui backup. Modelos e a
fila SQLite do TC continuam no diretório persistido `training/model`.

Para conferir a sintaxe sem exibir valores de ambiente, execute:

```bash
docker compose -f docker-compose.yml config --quiet
```

Uma imagem antiga já distribuída pode conter arquivos copiados anteriormente;
reconstruir não apaga camadas antigas. Se houver confirmação de credencial
incluída numa imagem antiga, remova a imagem dos destinos correspondentes e
rotacione essa credencial.

## Desenvolvimento com recarga automática

O ambiente de desenvolvimento usa `docker-compose.dev.yml` de forma independente.
Os comandos antigos com `docker-compose.yml` continuam disponíveis para o ambiente existente.
Requer Docker Engine e Docker Compose v2 (2.20 ou superior).

Mantenha os repositórios lado a lado:

```text
~/git/dev/
├── docker/
├── myfinance/
└── transaction_classifier/
```

O nome encontrado no disco para o classificador é `transaction_classifier`.
Se a pasta se chamar `transaction-classifier`, ajuste `CLASSIFIER_PATH` em `.env.dev`.
Os caminhos relativos são resolvidos a partir deste repositório Docker.
Para outra estrutura, configure `MYFINANCE_PATH`, `CLASSIFIER_PATH` e um caminho
absoluto para `DEV_DOCKERFILE` em `.env.dev`.

### Primeiro uso

Execute na pasta `~/git/dev/docker`:

```bash
cp .env.dev.example .env.dev
id -u
id -g
```

Ajuste `DEV_UID` e `DEV_GID` em `.env.dev` com os valores acima. Isso permite que
arquivos como migrations sejam criados com seu usuário. O arquivo `.env.dev` é
ignorado pelo Git; as credenciais de exemplo servem apenas para desenvolvimento.

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml config --quiet
docker compose --env-file .env.dev -f docker-compose.dev.yml up --build -d
docker compose --env-file .env.dev -f docker-compose.dev.yml exec app-myfin python manage.py migrate
docker compose --env-file .env.dev -f docker-compose.dev.yml exec app-myfin python manage.py createsuperuser
```

O serviço `investment-history` sobe junto com o ambiente de desenvolvimento e
processa a fila de investimentos com a mesma imagem, código e configuração do
aplicativo, sem publicar portas. O botão de atualizar investimentos agenda a
consulta e o registro das movimentações; o trabalhador processa essa consulta
em segundo plano. Após mudar o código do trabalhador, execute
`docker compose --env-file .env.dev -f docker-compose.dev.yml restart investment-history`.
Se mudar dependências ou variáveis, reconstrua/recrie os serviços correspondentes.

Acesse **http://localhost:8000**. A porta pode ser alterada em `MYFIN_DEV_PORT`.
O MySQL está disponível no computador em `127.0.0.1:3306`, com banco e usuário
`myfinance_dev` e senha definida em `DEV_MYSQL_PASSWORD` no `.env.dev`.
Clientes locais devem usar TCP com host `127.0.0.1`, em vez do socket de `localhost`.
Dentro dos containers, o endereço continua sendo `mysql-myfin:3306`.
O Redis é acessível apenas pela rede interna dos serviços.
O MySQL começa com um banco vazio; o volume deste ambiente é separado do existente.
Os arquivos de mídia são os da pasta `media/` do repositório externo do MyFinance.

### Fluxo diário

```bash
# Iniciar novamente, sem reconstruir imagens
docker compose --env-file .env.dev -f docker-compose.dev.yml up -d

# Acompanhar logs e mensagens de recarga
docker compose --env-file .env.dev -f docker-compose.dev.yml logs -f app-myfin

# Gerar e aplicar migrations após alterações de models
docker compose --env-file .env.dev -f docker-compose.dev.yml exec app-myfin python manage.py makemigrations
docker compose --env-file .env.dev -f docker-compose.dev.yml exec app-myfin python manage.py migrate

# Parar e remover containers, preservando os volumes de dados
docker compose --env-file .env.dev -f docker-compose.dev.yml down
```

Alterações de Python reiniciam o servidor automaticamente. Para HTML, CSS e
JavaScript, salve e atualize a página; a atualização do navegador é manual.
Arquivos estáticos são servidos pelo Django em desenvolvimento, sem Nginx ou
`collectstatic`. As configurações específicas ficam em `dev/`, montadas no
container, sem alterações nos outros repositórios. `dev_asgi.py` inicializa o
Django antes das rotas de WebSocket e preserva a aplicação Channels.

Quando mudar `pyproject.toml` ou `poetry.lock`, atualize o lock no repositório
correspondente e execute `up --build -d` novamente. Alterações de `.env.dev`
exigem `up -d` para recriar os serviços afetados.

Se o build falhar com `Temporary failure resolving` em Linux, configure
`DEV_BUILD_NETWORK=host` em `.env.dev` e repita o build. Essa opção altera
somente a rede usada durante a construção das imagens.

### Classificador opcional

O classificador fica no perfil `classifier`; o ambiente básico sobe sem ele.
Para habilitar o serviço e sua recarga automática:

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml --profile classifier up --build -d
```

A documentação da API estará em **http://localhost:8112/docs**.
O classificador acessa o Django por `http://app-myfin:8000`, e o Django acessa
o classificador por `http://transaction-classifier:8112`.
Com o perfil desabilitado, funcionalidades que dependem de classificação ficam indisponíveis.

Para fluxos de treinamento que utilizam OAuth2, cadastre uma aplicação
confidencial com grant `client_credentials` no admin do banco de desenvolvimento
(`/admin/oauth2_provider/application/`), associada ao usuário do classificador.
Preencha `DEV_CLASSIFIER_CLIENT_ID` e `DEV_CLASSIFIER_CLIENT_SECRET` em `.env.dev`
com as credenciais geradas e execute o comando de inicialização do perfil novamente.
As permissões do usuário associado determinam os dados acessíveis ao treinamento.

Para parar também o classificador:

```bash
docker compose --env-file .env.dev -f docker-compose.dev.yml --profile classifier down
```

### Repositórios e dados

Edite, atualize e faça commits diretamente em `~/git/dev/myfinance` e
`~/git/dev/transaction_classifier`. O código é compartilhado com os containers
por bind mounts, e o build instala apenas as dependências. As pastas internas
`docker/myfinance` e `docker/transaction_classifier` não são necessárias para o
ambiente de desenvolvimento. O Compose e o Dockerfile antigos ainda dependem
dessas pastas para o fluxo existente.

Após restaurar um dump com a aplicação já aberta, as listas de categorias podem
continuar vazias no cache da aba. Se os gráficos ficarem vazios, execute no console
do navegador para buscar essas listas novamente:

```javascript
sessionStorage.removeItem('categories');
sessionStorage.removeItem('subcategories');
location.reload();
```

Os volumes `mysql-dev-data` e `redis-dev-data` pertencem ao projeto Compose
`myfinance-dev`. O comando `down` os preserva; adicionar `--volumes` apaga os dados
de desenvolvimento. Use sempre o arquivo de desenvolvimento sozinho, sem
combiná-lo com `docker-compose.yml`.

## Ambiente existente

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

### Acessando o MySQL

> mysql -u USUARIO -h 127.0.0.1 -P 3307 -p


## Repositórios e trabalhador de investimentos em produção

`myfinance/` e `transaction_classifier/` são clones independentes, não submódulos.
Atualize cada repositório com seu próprio Git. O repositório de infraestrutura
não fixa seus commits nem rastreia seus arquivos. Ao preparar um servidor novo,
clone ambos nos diretórios indicados antes de construir as imagens.

O serviço `investment-history` processa a fila persistida de movimentações da
Pluggy. Ele usa o código da imagem, sem montar o checkout por cima dela, e é
recriado pelo `mfupdate` com a mesma imagem do slot ativo. Não crie um
trabalhador avulso na rede do Compose.

Mantenha os backups de arquivos em `/docker/myfinance-backups`, fora do checkout
`/docker/myfinance`. Os backups de imagens continuam sendo gerenciados pelo
`mfupdate`. As cópias antigas de estáticos gerados foram preservadas no mesmo
diretório de backups; os arquivos servidos pelo Nginx ficam em `static/`.


## Atualização blue/green e inicialização no Alpine Linux

Execute `mfupdate` como antes, após atualizar este checkout de infraestrutura
com `git -C /docker/myfinance pull --ff-only`. O script atualiza somente o clone
`myfinance/`, constrói a imagem e alterna entre `app-myfin-blue` (`172.18.0.8`)
e `app-myfin-green` (`172.18.0.9`). A aplicação atual, o MySQL e o Redis continuam
em execução durante a preparação.

O fluxo faz `check`, verifica migrations, salva o backup quando necessário e
aplica as migrations antes de gerar os estáticos exclusivos do novo slot.
Depois sobe o novo servidor e valida o banco e uma resposta HTTP de sucesso ou
redirecionamento. Só então testa e recarrega o Nginx. Uma segunda validação HTTP,
pelo Nginx, exige o cabeçalho do slot novo antes de aposentar o antigo. Uma falha
nessa troca restaura a configuração e a seleção anteriores. As migrations já
aplicadas não são desfeitas.

Na **primeira adoção**, o `app-myfin` existente é substituído pelo slot blue.
O Nginx precisa ser recriado uma vez para montar o diretório de configuração e
os estáticos dos slots; espere uma breve interrupção nessa etapa. Nas próximas
atualizações ele recebe apenas um reload. Se o container `nginx-proxy` estiver
ativo, ele também recebe um reload nessa primeira adoção para resolver novamente
o endereço de `nginx-myfin` na rede externa. O endereço interno `app-myfin:8000`
passa a ser um alias de rede do Nginx, que escuta também na porta 8000 e encaminha
para o slot ativo. Clientes com conexões antigas precisam reconectar após a
retirada do container legado. As portas publicadas na VM permanecem iguais.

`TEST_TIMEOUT` (60 segundos por padrão) limita cada etapa de espera HTTP direta
e pelo proxy; as migrations são síncronas e não usam esse prazo.
`DRAIN_TIMEOUT` (60 segundos por padrão) limita a espera pelos workers antigos
do Nginx, que conservam requisições e WebSockets abertos durante o reload.
Depois desse prazo, o app antigo recebe a parada do Docker, com mais 10 segundos
de tolerância; conexões restantes podem ser encerradas. O worker de investimentos
é recriado na imagem nova após a troca do app. Uma falha nessa finalização é
reportada mantendo o slot novo ativo.

O estado fica em `.mfdeploy/`, ignorado pelo Git: `active` indica o slot,
`blue.yml`/`green.yml` fixam as imagens por tags exclusivas, `blue.nginx.conf`/`green.nginx.conf` guardam os upstreams por slot, `nginx/` contém a
configuração publicada e `assets/` contém os estáticos. Preserve esse diretório
e as imagens referenciadas para reiniciar a mesma versão após reboot. Não edite
a seleção manualmente: ela precisa corresponder ao upstream do Nginx.
O script recusa execuções concorrentes com `.mfdeploy/lock`. Após uma interrupção
abrupta, confirme que não há atualização em execução antes de remover esse
subdiretório de lock e repetir o comando.

Use o wrapper **`mfcompose` em produção** para carregar o perfil e a imagem
persistidos, por exemplo:

```sh
/docker/myfinance/mfcompose ps
/docker/myfinance/mfcompose up -d
/docker/myfinance/mfcompose logs --tail 100 app-myfin-blue
```

O wrapper usa `/docker/myfinance` por padrão; `BASEDIR` permite outro checkout.
Ele detecta Compose v2 (`docker compose`) e mantém suporte ao v1 com profiles
(1.28 ou superior). Antes da primeira atualização, seleciona o perfil `legacy`.
Não execute `docker compose up` diretamente em produção: ele não carrega a
seleção persistida. Ao executar `up`, o wrapper reconcilia o upstream com o slot
salvo e recarrega o Nginx, inclusive se houve interrupção durante a troca.
O Compose de desenvolvimento continua independente.

O `mfupdate` instala o serviço `myfinance.init.d` em `/etc/init.d/myfinance`
antes da troca do proxy. O OpenRC usa `mfcompose` para iniciar e parar o ambiente,
preservando as redes existentes durante o boot e restaurando o slot ativo.
O arquivo `myfinance.service` também usa o wrapper; ajuste seus caminhos e
`BASEDIR` ao instalar em um servidor com systemd.

Os estáticos novos ficam isolados dos antigos durante a preparação. O Nginx
busca primeiro no slot ativo e depois no anterior, preservando arquivos com hash
usados por páginas antigas. Arquivos com a mesma URL e conteúdo diferente passam
a servir a versão nova; use nomes com hash para coexistência completa. Cada slot
mantém seu diretório entre atualizações, sem `collectstatic --clear`, para não
apagar referências antigas durante a transição. Media continua compartilhada.

## Migrações na atualização

Se houver migrations pendentes, o `mfupdate` salva um dump MySQL privado **antes
de executar qualquer migration**, em `/docker/myfinance-backups` por padrão.
`MIGRATION_BACKUP_DIR` permite escolher outro diretório. Uma falha de backup ou
migration interrompe a implantação antes de trocar o tráfego. O dump permanece
para recuperação; o script não restaura o banco automaticamente.

As duas versões compartilham o banco durante a atualização. As migrations
precisam ser compatíveis com a versão anterior: adicione estruturas novas antes
de usá-las e remova estruturas antigas em uma atualização posterior. O backup
de imagem não desfaz alterações no banco, mesmo quando a validação HTTP falha.
`BACKUP_KEEP` mantém até três backups de imagem por padrão. A limpeza preserva
as tags das duas imagens referenciadas pelo estado dos slots, além dos backups,
e não remove volumes.


## Recuperação de senha

Atualize também o MyFinance. A migração `login.0008` cria a fila curta de envio,
processada pelo serviço `password-reset-email`. O `mfupdate` fixa esse worker na
mesma imagem da aplicação e o recria após a troca do slot, junto do worker de
investimentos. Os tokens de recuperação não são armazenados na fila.

No `.env` de produção, configure `PUBLIC_BASE_URL`, `EMAIL_BACKEND`,
`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN`,
`GMAIL_SENDER_EMAIL` e `DEFAULT_FROM_EMAIL`. As credenciais Gmail são separadas
das do login social e são repassadas pelo bloco compartilhado de ambiente.
O backend de produção é `login.email_backend.GmailBackend`.

O procedimento de autorização Google e os comandos estão no documento
`myfinance/docs/recuperacao-senha.md`. Em desenvolvimento, o worker herda o `.env`
do checkout montado; com `DEBUG` ativo o padrão é enviar ao console, sem chamar
Gmail. Não use esse backend de console em produção.

Atualize o Compose e publique pelo `mfupdate`. No desenvolvimento, aplique
`python manage.py migrate` no serviço `app-myfin` e suba também o serviço
`password-reset-email` com o mesmo Compose de desenvolvimento. Reiniciar um
container existente não adiciona serviços nem atualiza o ambiente.

As configurações Nginx deste repositório omitem as URLs de recuperação com token
dos access logs. Configure a mesma proteção no proxy HTTPS externo e em outros
proxies que registrem essas URLs antes de liberar o recurso. Valide com `nginx -t`
antes de recarregar. A configuração local correspondente está no repositório
`reverse_proxy/nginx-proxy.conf`.
