import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re

# --- Configuração da Página ---
st.set_page_config(page_title="Gestão de Ponto e Benefícios", layout="wide")

# ==============================================================================
# FUNÇÕES AUXILIARES (Página de Análise)
# ==============================================================================

def limpar_celula_tempo(valor_celula):
    """Lê horário do Excel, suportando HH:MM e HH:MM:SS, retorna timedelta."""
    if pd.isna(valor_celula):
        return None
    s = str(valor_celula).strip()
    s = re.sub(r'[^\d:]', '', s) 
    if not s:
        return None
    try:
        t = datetime.strptime(s, "%H:%M")
        return timedelta(hours=t.hour, minutes=t.minute)
    except ValueError:
        try:
            t = datetime.strptime(s, "%H:%M:%S")
            return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        except ValueError:
            return None

def formatar_visual(td):
    """Formata timedelta para HH:MM visual."""
    if td is None:
        return ""
    total_segundos = int(td.total_seconds())
    horas = total_segundos // 3600
    minutos = (total_segundos % 3600) // 60
    return f"{horas:02d}:{minutos:02d}"

def processar_ponto(uploaded_file):
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, header=None)
        else:
            df = pd.read_excel(uploaded_file, header=None)
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        return None, None, 0

    try:
        nome_funcionario = df.iloc[18, 0]
    except:
        nome_funcionario = "Nome não encontrado"

    # Mapeamento de linhas para horários padrão
    linhas_horario = {
        'Seg': 10, 'Ter': 12, 'Qua': 14, 'Qui': 17, 'Sex': 19, 'Sáb': 22, 'Dom': None
    }
    
    agendamento = {}

    for dia_chave, indice_linha in linhas_horario.items():
        if indice_linha is None:
            agendamento[dia_chave] = None
            continue
        
        ent1 = limpar_celula_tempo(df.iloc[indice_linha, 24])
        sai1 = limpar_celula_tempo(df.iloc[indice_linha, 26])
        ent2 = limpar_celula_tempo(df.iloc[indice_linha, 28])
        
        agendamento[dia_chave] = {
            'std_ent1': ent1,
            'std_sai1': sai1,
            'std_ent2': ent2
        }

    linhas_dados = df.iloc[31:].copy()
    dias_com_atraso = []
    total_ocorrencias_geral = 0
    tolerancia = timedelta(minutes=5)

    for idx, row in linhas_dados.iterrows():
        data_str = str(row[0])
        if pd.isna(data_str) or '-' not in data_str: continue
        partes = data_str.split('-')
        if len(partes) < 2: continue
        
        data_val = partes[0].strip()
        dow_val = partes[1].strip()
        
        if 'Sáb' in dow_val or 'Sab' in dow_val: chave_dow = 'Sáb'
        elif 'Dom' in dow_val: chave_dow = 'Dom'
        else: chave_dow = dow_val
            
        if chave_dow not in agendamento or agendamento[chave_dow] is None: continue
        padrao = agendamento[chave_dow]
        
        real_ent1 = limpar_celula_tempo(row[2]) 
        real_sai1 = limpar_celula_tempo(row[5]) 
        real_ent2 = limpar_celula_tempo(row[8]) 
        
        motivos = []

        # Regra 1: Chegada
        if padrao['std_ent1'] and real_ent1:
            limite = padrao['std_ent1'] + tolerancia
            if real_ent1 > limite:
                motivos.append(f"Manhã ({formatar_visual(real_ent1)})")

        # Regra 2: Volta Almoço
        if padrao['std_ent2'] and padrao['std_sai1'] and real_sai1 and real_ent2:
            duracao = padrao['std_ent2'] - padrao['std_sai1']
            limite = real_sai1 + duracao + tolerancia
            if real_ent2 > limite:
                motivos.append(f"Volta Almoço (Lim {formatar_visual(limite)} vs Real {formatar_visual(real_ent2)})")

        if motivos:
            qtd = len(motivos)
            total_ocorrencias_geral += qtd
            dias_com_atraso.append({
                'Data': data_val,
                'Dia': chave_dow,
                'Qtd': qtd,
                'Detalhes': ", ".join(motivos)
            })
            
    return nome_funcionario, pd.DataFrame(dias_com_atraso), total_ocorrencias_geral

# ==============================================================================
# MENU LATERAL
# ==============================================================================

st.sidebar.title("Navegação")
pagina = st.sidebar.radio("Ir para:", ["📂 Análise de Ponto", "💰 Calc. Vale Alimentação"])

st.sidebar.markdown("---")
st.sidebar.info("Sistema de Gestão de RH")

# ==============================================================================
# PÁGINA 1: ANÁLISE DE PONTO
# ==============================================================================

if pagina == "📂 Análise de Ponto":
    st.title("📂 Análise de Atrasos (Ponto)")
    st.markdown("Faça o upload do arquivo para verificar atrasos na entrada e no almoço.")

    arquivo = st.file_uploader("Carregue o arquivo (XLSX ou CSV)", type=['csv', 'xlsx'])

    if arquivo:
        with st.spinner('Analisando dados...'):
            nome, df_resultado, total_ocorrencias = processar_ponto(arquivo)
        
        if nome:
            st.success(f"Funcionário: **{nome}**")
            
            # Guardar o total na sessão para usar na outra página (opcional, mas útil)
            st.session_state['ultimo_total_atrasos'] = total_ocorrencias
            
            col1, col2 = st.columns(2)
            with col1:
                qtd_dias = len(df_resultado) if df_resultado is not None else 0
                st.metric("Dias com Atraso", qtd_dias)
            with col2:
                st.metric("Total de Ocorrências", total_ocorrencias, delta_color="inverse")
            
            st.divider()
            
            if df_resultado is not None and not df_resultado.empty:
                st.warning(f"Irregularidades encontradas: {total_ocorrencias}")
                st.dataframe(
                    df_resultado, 
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "Qtd": st.column_config.NumberColumn("Qtd", format="%d", width="small")
                    }
                )
            else:
                st.balloons()
                st.success("Tudo limpo! Nenhum atraso.")

# ==============================================================================
# PÁGINA 2: CÁLCULO DE VALE ALIMENTAÇÃO
# ==============================================================================

elif pagina == "💰 Calc. Vale Alimentação":
    st.title("💰 Calculadora de Vale Alimentação")
    st.markdown("Calcule o valor final do benefício baseado no cargo e penalidades por atraso.")

    # 1. Definição de Valores
    tabela_cargos = {
        "Junior": 252.07,
        "Premium": 348.45,
        "Senior": 444.84,
        "Master": 548.64
    }

    # 2. Layout de Inputs
    col_input1, col_input2 = st.columns(2)

    with col_input1:
        cargo_selecionado = st.selectbox(
            "Selecione o Cargo", 
            list(tabela_cargos.keys())
        )
    
    # Tenta pegar o valor da outra página se existir, senão 0
    valor_inicial_atrasos = st.session_state.get('ultimo_total_atrasos', 0)

    with col_input2:
        qtd_atrasos = st.number_input(
            "Quantidade Total de Atrasos", 
            min_value=0, 
            value=valor_inicial_atrasos, # Sugere o valor achado na análise
            step=1,
            help="Insira o número total de ocorrências no mês."
        )

    st.divider()

    # 3. Lógica de Cálculo
    valor_base_mensal = tabela_cargos[cargo_selecionado]
    valor_diario = valor_base_mensal / 30  # Base 30 dias
    
    valor_final = 0.0
    mensagem_penalidade = ""
    cor_alerta = "green" # green, orange, red

    # Regras de Penalidade
    if qtd_atrasos < 3:
        # 0 a 2 atrasos: Recebe integral
        valor_final = valor_base_mensal
        mensagem_penalidade = "✅ Nenhuma penalidade aplicada (Menos de 3 atrasos)."
        cor_alerta = "success"

    elif qtd_atrasos == 3:
        # 3 atrasos: Perde 2 dias
        desconto = 2 * valor_diario
        valor_final = valor_base_mensal - desconto
        mensagem_penalidade = f"⚠️ Penalidade: Desconto de 2 dias (R$ {desconto:.2f})."
        cor_alerta = "warning"

    elif 4 <= qtd_atrasos <= 7:
        # 4 a 7 atrasos: Perde 7 dias
        desconto = 7 * valor_diario
        valor_final = valor_base_mensal - desconto
        mensagem_penalidade = f"⛔ Penalidade: Desconto de 7 dias (R$ {desconto:.2f})."
        cor_alerta = "error"

    else:
        # 8 ou mais atrasos: Valor fixo da cesta
        valor_final = 148.27
        mensagem_penalidade = "🚨 Penalidade Máxima: Redução para valor fixo de cesta básica."
        cor_alerta = "error"

    # 4. Exibição dos Resultados
    st.subheader("Resultado do Cálculo")

    col_res1, col_res2, col_res3 = st.columns(3)

    with col_res1:
        st.metric("Valor Base (30 dias)", f"R$ {valor_base_mensal:.2f}")

    with col_res2:
        # Mostra a diferença como negativo em vermelho
        diferenca = valor_final - valor_base_mensal
        st.metric("Desconto / Ajuste", f"R$ {diferenca:.2f}", delta=f"{diferenca:.2f}")

    with col_res3:
        st.metric("Valor a Receber", f"R$ {valor_final:.2f}")

    # Caixa de mensagem explicativa
    if cor_alerta == "success":
        st.success(mensagem_penalidade)
    elif cor_alerta == "warning":
        st.warning(mensagem_penalidade)
    else:
        st.error(mensagem_penalidade)

    # Detalhe do cálculo matemático (opcional, para transparência)
    with st.expander("Ver detalhes do cálculo"):
        st.write(f"**Cargo:** {cargo_selecionado}")
        st.write(f"**Valor Diário (Base/30):** R$ {valor_diario:.4f}")
        st.write(f"**Ocorrências:** {qtd_atrasos}")
        st.write(f"**Regra Aplicada:** {mensagem_penalidade}")
```

### O que há de novo:

1.  **Menu Lateral:** Agora você verá uma barra à esquerda para escolher entre "Análise de Ponto" (a ferramenta que já criamos) e "Calc. Vale Alimentação" (a nova página).
2.  **Página de Cálculo:**
    * Você seleciona o cargo (Junior, Premium, Senior, Master).
    * Você digita o número de atrasos.
    * **Integração Inteligente:** Se você analisou um arquivo na primeira página, o sistema "sugere" automaticamente o número de atrasos encontrados no campo de input da calculadora (mas você pode alterar manualmente se quiser).
3.  **Regras Aplicadas:**
    * **< 3 atrasos:** Valor integral.
    * **= 3 atrasos:** Desconta o valor de 2 dias (Valor Base / 30 * 2).
    * **4 a 7 atrasos:** Desconta o valor de 7 dias (Valor Base / 30 * 7).
    * **8+ atrasos:** Valor fixo de R$ 148,27.

Basta salvar e rodar `streamlit run app.py` novamente!
