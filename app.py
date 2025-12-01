import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re

# Configuração da página
st.set_page_config(page_title="Analisador de Ponto", layout="wide")

def limpar_celula_tempo(valor_celula):
    """Converte valores do Excel para objetos timedelta."""
    if pd.isna(valor_celula):
        return None
    s = str(valor_celula).strip()
    # Remove caracteres estranhos, mantendo apenas números e dois pontos
    s = re.sub(r'[^\d:]', '', s) 
    if not s:
        return None
    try:
        t = datetime.strptime(s, "%H:%M")
        return timedelta(hours=t.hour, minutes=t.minute)
    except:
        return None

def processar_ponto(uploaded_file):
    # Carregamento do arquivo
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, header=None)
        else:
            df = pd.read_excel(uploaded_file, header=None)
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        return None, None, 0

    # 1. Obter Nome do Funcionário
    try:
        nome_funcionario = df.iloc[18, 0]
    except:
        nome_funcionario = "Nome não encontrado"

    # 2. Configurar Horários Padrão (Mapeamento Fixo)
    linhas_horario = {
        'Seg': 10, 'Ter': 12, 'Qua': 14, 'Qui': 17, 'Sex': 19, 'Sáb': 22, 'Dom': None
    }
    
    agendamento = {}

    for dia_chave, indice_linha in linhas_horario.items():
        if indice_linha is None:
            agendamento[dia_chave] = None
            continue
        
        # Extração dos horários padrão das colunas fixas
        ent1 = limpar_celula_tempo(df.iloc[indice_linha, 24]) # Y
        sai1 = limpar_celula_tempo(df.iloc[indice_linha, 26]) # AA
        ent2 = limpar_celula_tempo(df.iloc[indice_linha, 28]) # AC
        sai2 = limpar_celula_tempo(df.iloc[indice_linha, 32]) # AG (Saída 2)
        
        agendamento[dia_chave] = {
            'std_ent1': ent1,
            'std_sai1': sai1,
            'std_ent2': ent2,
            'std_sai2': sai2
        }

    # 3. Processar Dados Reais (começam na linha 32 do Excel, índice 31 do DF)
    linhas_dados = df.iloc[31:].copy()
    dias_com_atraso = []
    total_ocorrencias_geral = 0
    tolerancia = timedelta(minutes=5)

    for idx, row in linhas_dados.iterrows():
        data_str = str(row[0])
        
        # Ignora linhas que não são datas
        if pd.isna(data_str) or '-' not in data_str:
            continue
            
        partes = data_str.split('-')
        if len(partes) < 2:
            continue
        
        data_val = partes[0].strip()
        dow_val = partes[1].strip()
        
        # Normalização do dia da semana
        if 'Sáb' in dow_val or 'Sab' in dow_val:
            chave_dow = 'Sáb'
        elif 'Dom' in dow_val:
            chave_dow = 'Dom'
        else:
            chave_dow = dow_val
            
        # Pula se não houver horário cadastrado para o dia (ex: Domingo)
        if chave_dow not in agendamento or agendamento[chave_dow] is None:
            continue
            
        padrao = agendamento[chave_dow]
        
        # Leitura dos horários REAIS nas colunas correspondentes
        real_ent1 = limpar_celula_tempo(row[2])  # Coluna C
        real_sai1 = limpar_celula_tempo(row[5])  # Coluna F
        real_ent2 = limpar_celula_tempo(row[8])  # Coluna I
        real_sai2 = limpar_celula_tempo(row[11]) # Coluna L

        motivos = []

        # --- REGRA 1: Entrada 1 (Atraso na chegada) ---
        if padrao['std_ent1'] and real_ent1:
            limite_ent1 = padrao['std_ent1'] + tolerancia
            if real_ent1 > limite_ent1:
                motivos.append(f"Chegada Tardia ({str(real_ent1)[:-3]})")

        # --- REGRA 2: Entrada 2 (Volta do Almoço) ---
        # Atraso só conta se ultrapassar (Saída Real + Duração Padrão + 5min)
        if padrao['std_ent2'] and padrao['std_sai1'] and real_sai1 and real_ent2:
            duracao_almoco_padrao = padrao['std_ent2'] - padrao['std_sai1']
            limite_ent2 = real_sai1 + duracao_almoco_padrao + tolerancia
            
            if real_ent2 > limite_ent2:
                motivos.append(f"Volta Almoço Tardia ({str(real_ent2)[:-3]})")

        # --- REGRA 3: Saída 2 (Saída Antecipada) ---
        # Conta se a pessoa saiu antes do horário padrão (-5 min de tolerância)
        if padrao['std_sai2'] and real_sai2:
            limite_sai2 = padrao['std_sai2'] - tolerancia
            if real_sai2 < limite_sai2:
                motivos.append(f"Saída Antecipada ({str(real_sai2)[:-3]})")

        # Se houve ocorrências no dia, adiciona à lista
        if len(motivos) > 0:
            qtd_dia = len(motivos)
            total_ocorrencias_geral += qtd_dia
            dias_com_atraso.append({
                'Data': data_val,
                'Dia da Semana': chave_dow,
                'Qtd': qtd_dia,
                'Detalhes': ", ".join(motivos)
            })
            
    return nome_funcionario, pd.DataFrame(dias_com_atraso), total_ocorrencias_geral

# --- Interface Visual do Site ---

st.title("🕒 Analisador de Ponto (Regra Flexível)")
st.markdown("""
Esta ferramenta analisa o cartão ponto focando em:
1. **Atrasos na Chegada**
2. **Atrasos na Volta do Almoço** (Calculado sobre o horário real de saída)
3. **Saídas Antecipadas** (Antes do horário final)
""")

arquivo = st.file_uploader("Carregue o arquivo (XLSX ou CSV)", type=['csv', 'xlsx'])

if arquivo:
    with st.spinner('Processando...'):
        nome, df_resultado, total_ocorrencias = processar_ponto(arquivo)
    
    if nome:
        st.success(f"Funcionário: **{nome}**")
        
        # Métricas no topo
        col1, col2 = st.columns(2)
        with col1:
            qtd_dias = len(df_resultado) if df_resultado is not None else 0
            st.metric("Dias com Atraso", qtd_dias)
        with col2:
            st.metric("Total de Ocorrências", total_ocorrencias, delta_color="inverse")
        
        st.divider()
        
        if df_resultado is not None and not df_resultado.empty:
            st.warning("Lista detalhada de irregularidades:")
            st.dataframe(
                df_resultado, 
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Qtd": st.column_config.NumberColumn(
                        "Falhas",
                        help="Número de falhas neste dia",
                        format="%d"
                    )
                }
            )
        else:
            st.balloons()
            st.success("Nenhuma irregularidade encontrada!")
