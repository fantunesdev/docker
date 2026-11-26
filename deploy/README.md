# CI/CD do MyFinance

O workflow `.github/workflows/myfinance.yml` pertence ao repositório
`fantunesdev/myfinance`. Pull requests para `main` executam os testes Python,
JavaScript, as verificações do deploy e o build. Pushes em `main` também publicam
uma imagem privada em `ghcr.io/fantunesdev/myfinance:<SHA>` e, quando habilitado,
executam o deploy por digest. `workflow_dispatch` permite repetir o fluxo na
`main`; commits que já foram ultrapassados são ignorados no deploy.

A imagem usa o Dockerfile e a lista de arquivos permitidos deste repositório.
Nenhum segredo de produção é necessário para construir ou testar. O banco de
testes é SQLite em memória; os testes do deploy usam comandos Docker simulados,
exceto a renderização do Compose, que não precisa do daemon. Esses testes não
substituem validação de migrations e funcionalidades específicas do MySQL nem
os testes de navegador existentes. A imagem de produção é construída somente
depois dos testes, com dependências do lock e identificação OCI do commit.

## Preparação

1. Publique as alterações deste repositório e anote o SHA completo do commit.
   Atualize o checkout `/docker/myfinance` da VM para esse commit. O CI **não**
   atualiza a infraestrutura nem o classificador automaticamente.
2. Publique o workflow no repositório MyFinance. Em **Settings → Secrets and
   variables → Actions → Variables**, configure:

   | Variável | Valor |
   | --- | --- |
   | `MYFINANCE_INFRA_REF` | SHA completo de 40 caracteres do commit de infraestrutura instalado na VM |
   | `MYFINANCE_DEPLOY_ENABLED` | `true` para ativar o deploy automático; ausente desabilita apenas o deploy |
   | `MYFINANCE_SSH_HOST` | Alias SSH ou `usuario@host`; padrão `producao` |
   | `MYFINANCE_BASEDIR` | Caminho absoluto sem espaços; padrão `/docker/myfinance` |

3. Crie o environment **production**, limitado à branch `main`. Para publicação
   totalmente automática, deixe-o sem aprovação manual. Configure proteção da
   `main` exigindo o job `ci` antes do merge.
4. Cadastre um runner Linux dedicado no repositório MyFinance, com label
   `myfinance-deploy`, em uma máquina com acesso à rede da VM. Execute-o como
   usuário sem privilégios, separado dos jobs de teste. O runner precisa de
   Bash, Python 3, OpenSSH e HTTPS para GitHub. O job de deploy não faz checkout
   nem executa código de pull requests.
5. No usuário do runner, configure a chave SSH e o alias `producao`. Cadastre a
   chave pública no usuário de deploy da VM e a chave de host verificada no
   `known_hosts`. Valide `ssh -T -o BatchMode=yes -o StrictHostKeyChecking=yes
   producao true`. O pipeline não aceita senha ou chave de host desconhecida.
6. O usuário remoto precisa de acesso ao Docker, ao checkout, ao estado
   administrativo `.mfdeploy` e ao diretório de backups. Prepare o serviço e as
   permissões uma vez, conforme abaixo. O deploy não instala serviços nem chama
   `sudo`. A aplicação atual deve estar rodando. A VM precisa de HTTPS para GHCR.
7. Habilite GitHub Actions e a criação de packages no repositório. O workflow
   usa `GITHUB_TOKEN` com `packages: write` no CI e `packages: read` no deploy;
   o pacote deve permitir acesso ao repositório MyFinance. O token temporário
   passa pela entrada padrão do SSH, fica em um diretório Docker temporário
   na VM e é removido ao finalizar. Não é necessário salvar um PAT na VM.

O checkout da infraestrutura no CI usa `GITHUB_TOKEN`; se `fantunesdev/docker`
for privado, configure o secret `MYFINANCE_INFRA_TOKEN` com um token que tenha
somente acesso de leitura a esse repositório. O workflow usa esse secret quando
disponível. O token padrão do MyFinance não concede acesso automático a outro
repositório privado; PRs de forks não recebem o secret.

## Preparação administrativa do servidor

O serviço de boot é instalado uma vez por um administrador e atualizado
manualmente quando seu arquivo mudar. Em Alpine/OpenRC:

```sh
sudo install -m 0755 /docker/myfinance/myfinance.init.d /etc/init.d/myfinance
```

Em systemd, use `myfinance.service` com os caminhos ajustados ao checkout,
instalando-o em `/etc/systemd/system/myfinance.service` e executando
`sudo systemctl daemon-reload`. O deploy habitual não altera `/etc` e não
precisa de uma regra `NOPASSWD` para instalar serviços.

Se o estado foi criado por root, ajuste somente os diretórios administrativos e
os arquivos de controle, sem outro deploy em execução. Para o usuário `fernando`:

```sh
deploy_base=/docker/myfinance
deploy_owner=fernando
deploy_group=$(id -gn "$deploy_owner")
sudo mkdir -p "$deploy_base/.mfdeploy/nginx"
sudo chown "$deploy_owner:$deploy_group" "$deploy_base/.mfdeploy"
sudo chmod u+rwx "$deploy_base/.mfdeploy"
sudo find "$deploy_base/.mfdeploy" -maxdepth 1 -type f -exec chown "$deploy_owner:$deploy_group" {} +
sudo find "$deploy_base/.mfdeploy" -maxdepth 1 -type f -exec chmod u+rw {} +
for relative in nginx assets assets/blue assets/green assets/legacy; do
    if [ -d "$deploy_base/.mfdeploy/$relative" ]; then
        sudo chown "$deploy_owner:$deploy_group" "$deploy_base/.mfdeploy/$relative"
        sudo chmod u+rwx "$deploy_base/.mfdeploy/$relative"
    fi
done
if [ -f "$deploy_base/.mfdeploy/nginx/default.conf" ]; then
    sudo chmod a+r "$deploy_base/.mfdeploy/nginx/default.conf"
fi
```

Não aplique `chown -R` no checkout inteiro: o banco, mídia e estáticos gerados
pelos containers têm permissões próprias. Prepare também acesso ao checkout
Git e ao diretório de backups para o usuário de deploy. O `mfupdate` verifica
as permissões do estado antes de tocar no Docker, fazer build ou migrations e
interrompe com o caminho problemático quando é preciso corrigir o servidor.
Configurações legíveis do Nginx podem pertencer a root: a troca usa renomeação
sem confirmação, exigindo escrita no diretório, não no arquivo substituído.
O `mfcompose` publica a configuração com modo `0644`, inclusive durante o boot.

Referências oficiais: [runners próprios](https://docs.github.com/en/actions/how-tos/manage-runners/self-hosted-runners/add-runners),
[sintaxe dos workflows](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax).

## Publicação e falhas

O runner chama `deploy/ci-deploy.sh` na VM; ele autentica no GHCR e executa o
`mfupdate` com `DEPLOY_IMAGE` e `DEPLOY_COMMIT`. Nesse modo não há `git pull` da
aplicação nem build na VM. A imagem precisa estar fixada por digest, conter o
mesmo SHA aprovado e ter sido construída com o commit de infraestrutura
instalado na VM. Essas conferências acontecem antes das migrations.

O fluxo blue/green, backup antes de migrations, verificações HTTP e atualização
dos workers continuam sendo executados pelo `mfupdate`. Migrations não são
desfeitas se a troca falhar e precisam ser compatíveis com o aplicativo antigo.
A primeira adoção recria o Nginx; conexões longas podem ser encerradas ao acabar
o prazo de drenagem. Não há promessa de indisponibilidade zero.

O SHA e o digest são persistidos em `.mfdeploy/<slot>.commit` e
`.mfdeploy/<slot>.image`. Após atualizar os workers, o script registra no banco
uma versão como `v2.0.gabcdef123456`. Se o registro falhar, o job falha com
código 2, **a nova aplicação permanece ativa** e o arquivo
`.mfdeploy/version-registration-pending` guarda o SHA pendente. Não repita um
deploy completo apenas para registrar a versão: após resolver o problema,
sem outro deploy em execução, rode na VM:

```sh
cd /docker/myfinance
slot=$(cat .mfdeploy/active)
commit=$(cat .mfdeploy/version-registration-pending)
test "$commit" = "$(cat ".mfdeploy/$slot.commit")"
./mfcompose exec -T "app-myfin-$slot" python - "$commit" < deploy/register_version.py
# Somente depois do sucesso:
rm .mfdeploy/version-registration-pending
```

Se falhar depois da troca, confira `.mfdeploy/active`, os logs do workflow e os
workers antes de repetir o deploy. Uma falha de worker mantém o slot novo ativo.
O lock do `mfupdate` impede execuções simultâneas na VM e o workflow não cancela
um deploy por causa de outro push. Cancelamentos forçados ainda podem exigir
recuperação conforme o README principal.

O comando manual antigo, sem `DEPLOY_IMAGE`, continua construindo na VM. O
acionador em `~/git/bin/mfupdate` também mantém seu registro por contagem de
commits; ele é um caminho manual separado e não participa do novo pipeline.
Sua cópia versionada está em `deploy/mfupdate-remote`. As opções `-tc` e `-d`
atualizam somente as branches atuais do classificador e da infraestrutura,
respectivamente, sem publicar o MyFinance nem registrar versão. Podem ser
combinadas. A opção `-a` atualiza os três repositórios, na ordem MyFinance,
classificador e Docker. Com opções, o acionador executa os pulls diretamente
por SSH, sem depender da versão do script remoto e sem chamá-lo. Sem argumentos,
o acionador mantém o deploy manual do MyFinance.
O deploy não executa mais `builder prune` ou `image prune` globais. A manutenção
de caches do host e a retenção de imagens no GHCR devem ser feitas separadamente.

## Verificação local

```sh
for script in mfupdate mfcompose deploy/ci-deploy.sh; do sh -n "$script"; done
python3 -m unittest discover -s tests -v
# No checkout MyFinance, com as dependências instaladas:
poetry run pytest --ds=myfinance.test_settings tests
node --test tests/js/*.test.mjs
```

O pipeline constrói `linux/amd64`, correspondente à VM x86_64. Ajuste
`platforms` antes de usar outro tipo de servidor. Antes de habilitar a variável
de deploy, faça uma execução com ela desabilitada para validar testes, build e
permissões de publicação no GHCR.
