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

    def test_outras_acoes_funcionam_para_logada(self):
        # O bloqueio e so do signup; whatsapp continua valendo para logada.
        assert (
            detect_action("queria falar com alguém", is_anonymous=False).slug
            == "whatsapp"
        )
