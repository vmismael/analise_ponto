import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re
from fuzzywuzzy import fuzz

# --- Configuração da Página ---
st.set_page_config(page_title="Gestão Integrada (RH & Financeiro)", layout="wide")

# ==============================================================================
# FUNÇÕES AUXILIARES - GERAIS E PONTO
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
        # Lê Excel diretamente
        df = pd.read_excel(uploaded_file, header=None)
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        return None, None, 0

    try:
        nome_funcionario = df.iloc[18, 0]
    except:
        nome_funcionario = "Nome não encontrado"

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
            'std_ent1': ent1, 'std_sai1': sai1, 'std_ent2': ent2
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
        if padrao['std_ent1'] and real_ent1:
            limite = padrao['std_ent1'] + tolerancia
            if real_ent1 > limite:
                motivos.append(f"Manhã ({formatar_visual(real_ent1)})")

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
# FUNÇÕES AUXILIARES - FINANCEIRO (DRE)
# ==============================================================================

def limpar_valor_financeiro(valor):
    """Converte strings financeiras ou floats do Excel para float puro."""
    if pd.isna(valor) or str(valor).strip() == '':
        return 0.0
    
    if isinstance(valor, (int, float)):
        return float(valor)

    s = str(valor).strip().upper().replace('C', '').replace('D', '')
    s = s.replace('R$', '').strip()
    s = s.replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0

def buscar_por_classificacao(df, codigo):
    """Busca valor na coluna Movimento baseado na Classificação."""
    linha = df[df['Classificação'] == codigo]
    if not linha.empty:
        valor_bruto = linha['Movimento'].values[0]
        return limpar_valor_financeiro(valor_bruto)
    return 0.0

# ==============================================================================
# FUNÇÕES AUXILIARES - CONCILIAÇÃO (NOTAS vs BALANCETE)
# ==============================================================================

def limpar_valor_conciliacao(valor):
    """Converte valor (Excel float ou String BR) para float."""
    if pd.isna(valor) or valor == '':
        return None
    
    # Se o Excel já leu como número, retorna direto
    if isinstance(valor, (int, float)):
        return float(valor)
    
    # Converte para string se for texto
    v_str = str(valor).strip().upper()
    
    # Remove letras comuns em balancetes (D = Débito, C = Crédito)
    v_str = v_str.replace('D', '').replace('C', '')
    
    # Remove símbolos de moeda e espaços
    v_str = v_str.replace('R$', '').strip()
    
    # Lida com formatação BR (remove ponto de milhar, troca vírgula por ponto)
    try:
        # Ex: "1.200,50" -> Tira ponto, troca virgula
        if ',' in v_str and '.' in v_str:
            v_str = v_str.replace('.', '').replace(',', '.')
        elif ',' in v_str:
            v_str = v_str.replace(',', '.')
            
        return float(v_str)
    except ValueError:
        return None

def carregar_balancete_xlsx(file, col_valor_idx=16, col_nome_idx=2):
    try:
        # Lê o Excel sem cabeçalho para pegar pelo índice da coluna (A=0, B=1...)
        df = pd.read_excel(file, header=None)
        processed_data = []
        
        for index, row in df.iterrows():
            if len(row) > col_valor_idx:
                raw_val = row[col_valor_idx]
                # Pega o nome (Coluna C normalmente)
                nome = row[col_nome_idx] if len(row) > col_nome_idx else "Sem Descrição"
                
                val_float = limpar_valor_conciliacao(raw_val)
                
                if val_float is not None and val_float != 0:
                    processed_data.append({
                        'Origem_Linha': index + 1,
                        'Conta_Balancete': nome,
                        'Valor_Balancete': val_float
                    })
        return pd.DataFrame(processed_data)
    except Exception as e:
        st.error(f"Erro ao ler Balancete (XLSX): {e}")
        return pd.DataFrame()

def carregar_notas_xlsx(file, col_valor_idx=1, col_nome_idx=0):
    try:
        # Lê o Excel sem cabeçalho
        df = pd.read_excel(file, header=None)
        processed_data = []
        
        for index, row in df.iterrows():
            if len(row) > col_valor_idx:
                raw_val = row[col_valor_idx] # Coluna B (indice 1)
                nome = row[col_nome_idx]     # Coluna A (indice 0)
                
                val_float = limpar_valor_conciliacao(raw_val)
                
                if val_float is not None and val_float > 0:
                    # Verifica se não é cabeçalho lendo o nome
                    nome_str = str(nome).lower() if nome else ""
                    if nome_str not in ['débito', 'valor', 'total', 'nan', 'histórico', 'descrição']:
                        processed_data.append({
                            'Nota_Linha': index + 1,
                            'Descricao_Nota': nome,
                            'Valor_Nota': val_float
                        })
        return pd.DataFrame(processed_data)
    except Exception as e:
        st.error(f"Erro ao ler Notas (XLSX): {e}")
        return pd.DataFrame()

def encontrar_correspondencia(row_nota, df_balancete):
    valor_procurado = row_nota['Valor_Nota']
    desc_nota = str(row_nota['Descricao_Nota'])
    
    # Filtra por valor exato (com margem de erro float)
    matches = df_balancete[
        (df_balancete['Valor_Balancete'] > valor_procurado - 0.01) & 
        (df_balancete['Valor_Balancete'] < valor_procurado + 0.01)
    ].copy()
    
    status = "Não Encontrado"
    detalhe = ""
    match_row = None
    
    if len(matches) == 0:
        status = "Divergente (Não achou valor)"
    elif len(matches) == 1:
        status = "Conferido (Valor Único)"
        match_row = matches.iloc[0]
    else:
        # Desempate por Nome
        status = "Conferido (Desempate por Nome)"
        melhor_score = 0
        melhor_match = None
        
        for idx, m_row in matches.iterrows():
            score = fuzz.partial_ratio(desc_nota.lower(), str(m_row['Conta_Balancete']).lower())
            if score > melhor_score:
                melhor_score = score
                melhor_match = m_row
        
        match_row = melhor_match
        detalhe = f"Score Similaridade: {melhor_score}"

    return status, match_row, detalhe

# ==============================================================================
# MENU LATERAL
# ==============================================================================

st.sidebar.title("Navegação")
opcoes = [
    "📂 Análise de Ponto", 
    "💰 Calc. Vale Alimentação", 
    "📊 Análise DRE",
    "🕵️ Conciliação Notas vs Balancete"
]
pagina = st.sidebar.radio("Ir para:", opcoes)

st.sidebar.divider()

# ==============================================================================
# PÁGINA 1: ANÁLISE DE PONTO
# ==============================================================================

if pagina == "📂 Análise de Ponto":
    st.title("📂 Análise de Atrasos (Ponto)")
    st.markdown("Faça o upload do arquivo XLSX para verificar atrasos.")

    arquivo = st.file_uploader("Carregue o arquivo de Ponto (XLSX)", type=['xlsx'])

    if arquivo:
        with st.spinner('Analisando dados...'):
            nome, df_resultado, total_ocorrencias = processar_ponto(arquivo)
        
        if nome:
            st.success(f"Funcionário: **{nome}**")
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
                    hide_index=True
                )
            else:
                st.balloons()
                st.success("Tudo limpo! Nenhum atraso.")

# ==============================================================================
# PÁGINA 2: CÁLCULO DE VALE ALIMENTAÇÃO
# ==============================================================================

elif pagina == "💰 Calc. Vale Alimentação":
    st.title("💰 Calculadora de Vale Alimentação")
    
    tabela_cargos = {
        "Junior": 252.07, "Premium": 348.45, "Senior": 444.84, "Master": 548.64
    }

    col_input1, col_input2 = st.columns(2)
    with col_input1:
        cargo_selecionado = st.selectbox("Selecione o Cargo", list(tabela_cargos.keys()))
    
    valor_inicial_atrasos = st.session_state.get('ultimo_total_atrasos', 0)

    with col_input2:
        qtd_atrasos = st.number_input("Qtd Atrasos", min_value=0, value=valor_inicial_atrasos, step=1)

    st.divider()

    valor_base_mensal = tabela_cargos[cargo_selecionado]
    valor_diario = valor_base_mensal / 30 
    valor_final = 0.0
    
    if qtd_atrasos < 3:
        valor_final = valor_base_mensal
        st.success("✅ Sem penalidade (Menos de 3 atrasos).")
    elif qtd_atrasos == 3:
        desconto = 2 * valor_diario
        valor_final = valor_base_mensal - desconto
        st.warning(f"⚠️ Penalidade: Desconto de 2 dias (R$ {desconto:.2f}).")
    elif 4 <= qtd_atrasos <= 7:
        desconto = 7 * valor_diario
        valor_final = valor_base_mensal - desconto
        st.error(f"⛔ Penalidade: Desconto de 7 dias (R$ {desconto:.2f}).")
    else:
        valor_final = 148.27
        st.error("🚨 Penalidade Máxima: Cesta Básica Fixa.")

    col1, col2 = st.columns(2)
    col1.metric("Valor Base", f"R$ {valor_base_mensal:.2f}")
    col2.metric("A Receber", f"R$ {valor_final:.2f}")

# ==============================================================================
# PÁGINA 3: ANÁLISE DRE
# ==============================================================================

elif pagina == "📊 Análise DRE":
    st.sidebar.markdown("### Dados Mês Anterior")
    rol_anterior = st.sidebar.number_input("ROL Anterior (R$)", value=647538.80)
    lucro_anterior = st.sidebar.number_input("Lucro Líq. Anterior (R$)", value=228305.24)
    
    st.title("📊 Automação de Análise DRE")
    uploaded_file_dre = st.file_uploader("Upload DRE (XLSX)", type=['xlsx'])

    if uploaded_file_dre is not None:
        try:
            df_raw = pd.read_excel(uploaded_file_dre, header=None)
            
            # Tenta achar a linha de cabeçalho
            idx_header = df_raw[df_raw.apply(lambda row: row.astype(str).str.contains('Classificação').any(), axis=1)].index[0]
            df_raw.columns = df_raw.iloc[idx_header]
            df = df_raw[idx_header+1:].reset_index(drop=True)
            df.columns = df.columns.str.strip()
            
            receita_bruta = buscar_por_classificacao(df, '03.1.1')
            deducoes = buscar_por_classificacao(df, '03.1.2')
            custos_servicos = buscar_por_classificacao(df, '04.1')
            lucro_liquido_atual = buscar_por_classificacao(df, '05.1.1.01.001')
            
            rol_atual = receita_bruta - deducoes
            
            if rol_atual:
                margem_liquida = lucro_liquido_atual / rol_atual
            else:
                margem_liquida = 0

            st.divider()
            c1, c2 = st.columns(2)
            c1.metric("ROL Atual", f"R$ {rol_atual:,.2f}")
            c2.metric("Margem Líquida", f"{margem_liquida:.2%}")

        except Exception as e:
            st.error(f"Erro: {e}")

# ==============================================================================
# PÁGINA 4: CONCILIAÇÃO DE NOTAS
# ==============================================================================

elif pagina == "🕵️ Conciliação Notas vs Balancete":
    st.title("🕵️ Conciliação: Notas Fiscais vs Balancete")
    st.markdown("Verifique se as despesas da planilha de notas constam no balancete.")
    st.info("O sistema aceita arquivos **.xlsx**. Certifique-se que o Balancete tenha valores na **Coluna Q** e as Notas na **Coluna B**.")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("1. Balancete")
        balancete_file = st.file_uploader("Upload Balancete (.xlsx)", type=['xlsx'], key="conc_bal")

    with col2:
        st.subheader("2. Planilhas de Notas")
        notas_files = st.file_uploader("Upload Notas (.xlsx)", type=['xlsx'], accept_multiple_files=True, key="conc_notas")

    # Dicionário para organizar arquivos por mês
    arquivos_por_mes = {}

    if notas_files:
        for f in notas_files:
            # Tenta pegar mes.ano do nome do arquivo
            match = re.search(r'(\d{2}\.\d{4})', f.name)
            if match:
                mes_ano = match.group(1)
                arquivos_por_mes[mes_ano] = f
            else:
                arquivos_por_mes[f.name] = f

    if balancete_file and arquivos_por_mes:
        st.divider()
        
        meses_disponiveis = sorted(list(arquivos_por_mes.keys()))
        mes_selecionado = st.selectbox("Selecione o Mês das Notas:", meses_disponiveis)
        
        if st.button("Iniciar Análise de Conciliação"):
            file_nota = arquivos_por_mes[mes_selecionado]
            
            with st.spinner('Cruzando informações (Lendo Excel)...'):
                # Balancete: Col Q = índice 16, Col C (Nome) = índice 2
                df_balancete = carregar_balancete_xlsx(balancete_file, col_valor_idx=16, col_nome_idx=2)
                
                # Notas: Col B = índice 1, Col A (Nome) = índice 0
                df_notas = carregar_notas_xlsx(file_nota, col_valor_idx=1, col_nome_idx=0)
                
                if df_balancete.empty or df_notas.empty:
                    st.error("Erro ao processar. Verifique se as colunas B (Notas) e Q (Balancete) possuem dados.")
                else:
                    resultados = []
                    
                    progresso = st.progress(0)
                    total_notas = len(df_notas)
                    
                    for i, row in df_notas.iterrows():
                        status, match_row, detalhe = encontrar_correspondencia(row, df_balancete)
                        
                        res = {
                            'NOTA_Descricao': row['Descricao_Nota'],
                            'NOTA_Valor': row['Valor_Nota'],
                            'STATUS': status,
                            'BALANCETE_Conta': match_row['Conta_Balancete'] if match_row is not None else '---',
                            'BALANCETE_Valor': match_row['Valor_Balancete'] if match_row is not None else 0.0,
                            'Detalhe': detalhe
                        }
                        resultados.append(res)
                        progresso.progress((i + 1) / total_notas)
                    
                    df_final = pd.DataFrame(resultados)
                    
                    st.success("Análise Concluída!")
                    
                    total = len(df_final)
                    divergentes = len(df_final[df_final['STATUS'].str.contains("Divergente")])
                    conferidos = total - divergentes
                    
                    m1, m2, m3 = st.columns(3)
                    m1.metric("Total Lançamentos", total)
                    m2.metric("Conferidos", conferidos)
                    m3.metric("Divergentes", divergentes, delta_color="inverse")
                    
                    st.subheader("Detalhamento")
                    filtro = st.radio("Filtro:", ["Tudo", "Apenas Divergentes", "Apenas Conferidos"], horizontal=True)
                    
                    df_show = df_final
                    if filtro == "Apenas Divergentes":
                        df_show = df_final[df_final['STATUS'].str.contains("Divergente")]
                    elif filtro == "Apenas Conferidos":
                        df_show = df_final[df_final['STATUS'].str.contains("Conferido")]
                    
                    st.dataframe(
                        df_show.style.format({
                            'NOTA_Valor': 'R$ {:,.2f}', 
                            'BALANCETE_Valor': 'R$ {:,.2f}'
                        }).map(lambda v: 'color: red;' if 'Divergente' in str(v) else ('color: green;' if 'Conferido' in str(v) else ''), subset=['STATUS'])
                    )

    elif not balancete_file and not arquivos_por_mes:
        st.info("Aguardando upload dos arquivos XLSX.")
