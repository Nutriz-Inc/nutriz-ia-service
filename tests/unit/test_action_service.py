from app.services.action_service import detect_action


class TestPositivos:
    def test_signup_anonimo(self):
        action = detect_action("Como faço para me cadastrar?", is_anonymous=True)
        assert action is not None
        assert action.slug == "signup"
        assert action.label == "Criar conta"

    def test_signup_criar_conta(self):
        assert detect_action("Quero criar uma conta", is_anonymous=True).slug == "signup"

    def test_signup_comecar_a_doar(self):
        assert (
            detect_action("Quero começar a doar leite", is_anonymous=True).slug
            == "signup"
        )

    def test_login_anonimo(self):
        action = detect_action("quero fazer login", is_anonymous=True)
        assert action.slug == "login"
        assert action.label == "Entrar"

    def test_login_ja_tenho_conta(self):
        assert (
            detect_action("já tenho conta, quero entrar na minha conta", is_anonymous=True).slug
            == "login"
        )

    def test_whatsapp_falar_com_alguem(self):
        action = detect_action("queria falar com alguém", is_anonymous=True)
        assert action.slug == "whatsapp"
        assert action.label == "Falar no WhatsApp"

    def test_whatsapp_termo_direto(self):
        assert (
            detect_action("vocês têm whatsapp?", is_anonymous=False).slug == "whatsapp"
        )

    def test_collection_points_onde_doar(self):
        action = detect_action("onde posso doar perto de mim?", is_anonymous=True)
        assert action.slug == "collection_points"
        assert action.label == "Ver pontos de coleta"

    def test_collection_points_ponto_de_coleta(self):
        assert (
            detect_action("tem algum ponto de coleta?", is_anonymous=False).slug
            == "collection_points"
        )

    def test_articles_ordenha(self):
        action = detect_action("como faço a ordenha?", is_anonymous=True)
        assert action.slug == "articles"
        assert action.label == "Ler artigo completo"

    def test_articles_armazenamento(self):
        assert (
            detect_action("como armazenar o leite ordenhado?", is_anonymous=False).slug
            == "articles"
        )


class TestNegativos:
    def test_pergunta_generica_nao_gera_acao(self):
        assert detect_action("posso doar leite com bebê de 4 meses?", is_anonymous=True) is None

    def test_pergunta_clinica_nao_gera_acao(self):
        assert detect_action("qual a temperatura ideal do leite?", is_anonymous=True) is None

    def test_mensagem_vazia(self):
        assert detect_action("", is_anonymous=True) is None


class TestNegacao:
    def test_nao_precisa_cadastrar_o_frasco_nao_dispara_signup(self):
        # A palavra "cadastrar" aparece, mas o objeto e o frasco, nao a conta.
        assert detect_action("não precisa cadastrar o frasco", is_anonymous=True) is None

    def test_nao_preciso_me_cadastrar_nao_dispara_signup(self):
        assert detect_action("não preciso me cadastrar agora", is_anonymous=True) is None


class TestAcentuacao:
    def test_com_e_sem_acento_dao_mesmo_resultado(self):
        com = detect_action("Como faço a ordenha?", is_anonymous=True)
        sem = detect_action("Como faco a ordenha?", is_anonymous=True)
        assert com.slug == sem.slug == "articles"

    def test_cadastro_sem_acento(self):
        assert detect_action("quero me cadastrar", is_anonymous=True).slug == "signup"


class TestPrioridade:
    def test_signup_vence_articles(self):
        # casa signup (quero me cadastrar) e articles (como fazer a ordenha)
        action = detect_action(
            "quero me cadastrar e saber como fazer a ordenha", is_anonymous=True
        )
        assert action.slug == "signup"

    def test_collection_points_vence_articles(self):
        action = detect_action(
            "onde posso doar e como armazenar o leite", is_anonymous=True
        )
        assert action.slug == "collection_points"


class TestSignupSomenteAnonimo:
    def test_signup_nao_dispara_para_logada(self):
        # Mesma frase que dispara signup no anonimo nao pode disparar na logada.
        assert detect_action("Como faço para me cadastrar?", is_anonymous=False) is None

    def test_login_nao_dispara_para_logada(self):
        assert detect_action("quero fazer login", is_anonymous=False) is None

    def test_outras_acoes_funcionam_para_logada(self):
        # O bloqueio e so do signup; whatsapp continua valendo para logada.
        assert (
            detect_action("queria falar com alguém", is_anonymous=False).slug
            == "whatsapp"
        )


class TestNavegacaoParaTelas:
    """Acoes de tela interna: so para a nutriz logada."""

    def test_minhas_doacoes(self):
        action = detect_action("quero ir para minhas doações", is_anonymous=False)
        assert action is not None
        assert action.slug == "my_donations"
        assert action.label == "Ver minhas doacoes"

    def test_minhas_doacoes_com_outro_verbo(self):
        assert (
            detect_action("me leva pra tela de minhas doações", is_anonymous=False).slug
            == "my_donations"
        )

    def test_perfil(self):
        assert (
            detect_action("me leva pra tela de perfil", is_anonymous=False).slug
            == "profile"
        )

    def test_perfil_por_meus_dados(self):
        assert (
            detect_action("onde vejo meus dados?", is_anonymous=False).slug == "profile"
        )

    def test_conteudo_educativo(self):
        assert (
            detect_action("quero ver o conteúdo educativo", is_anonymous=False).slug
            == "content_hub"
        )

    def test_nova_doacao(self):
        assert (
            detect_action("quero fazer uma nova doação", is_anonymous=False).slug
            == "new_donation"
        )

    def test_nova_doacao_doar_de_novo(self):
        assert (
            detect_action("quero doar de novo", is_anonymous=False).slug
            == "new_donation"
        )

    def test_inicio(self):
        assert (
            detect_action("me leva para o início", is_anonymous=False).slug == "home"
        )


class TestNavegacaoNaoDisparaAToa:
    def test_anonimo_nao_recebe_tela_interna(self):
        # A rota nem existe no router publico do front.
        assert detect_action("quero ver minhas doações", is_anonymous=True) is None

    def test_pergunta_sobre_a_doacao_nao_vira_botao(self):
        # Falar da doacao nao e pedir para navegar.
        assert detect_action("quanto leite eu já doei?", is_anonymous=False) is None

    def test_inicio_de_processo_nao_vira_home(self):
        assert (
            detect_action("o que faço no início da ordenha?", is_anonymous=False) is None
        )

    def test_tema_especifico_ainda_vence_conteudo_educativo(self):
        # "como armazenar" continua indo para o artigo, nao para a central.
        assert (
            detect_action("como armazenar o leite?", is_anonymous=False).slug
            == "articles"
        )
