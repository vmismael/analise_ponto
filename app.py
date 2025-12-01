import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re

st.set_page_config(page_title="Analisador de Ponto Completo", layout="wide")

def limpar_celula_tempo(valor_celula):
    if pd.isna(valor_celula):
        return None
    s = str(valor_celula).strip()
    s = re.sub(r'[^\d:]', '', s) 
    if not s:
        return None
    try:
        t = datetime.strptime(s, "%H:%M")
        return timedelta(hours=t.hour, minutes=t.minute)
    except:
        return None

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

    # Configuração dos Horários Padrão
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
        sai2 = limpar_celula_tempo(df.iloc[indice_linha, 32]) # Adicionado Saída 2
        
        agendamento[dia_chave] = {
            'std_ent1': ent1,
            'std_sai1': sai1,
            'std_ent2': ent2,
            'std_sai2': sai2
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
        
        # Coletar Horários Reais
        real_ent1 = limpar_celula_tempo(row[2])  # C
        real_sai1 = limpar_celula_tempo(row[5])  # F
        real_ent2 = limpar_celula_tempo(row[8])  # I
        real_sai2 = limpar_celula_tempo(row[11]) # L (Confira se é L no seu arquivo, geralmente padrão Secullum)

        motivos = []

        # 1. Entrada 1 (Atraso na chegada)
        if padrao['std_ent1'] and real_ent1:
            limite = padrao['std_ent1'] + tolerancia
            if real_ent1 > limite:
                motivos.append(f"Chegada Tardia ({str(real_ent1)[:-3]})")

        # 2. Saída 1 (Atraso ao sair para o almoço)
        # Muitas empresas consideram sair tarde para o almoço como ocorrência
        if padrao['std_sai1'] and real_sai1:
            limite = padrao['std_sai1'] + tolerancia
            if real_sai1 > limite:
                motivos.append(f"Saída Almoço Tardia ({str(real_sai1)[:-3]})")

        # 3. Entrada 2 (Volta do Almoço - Regra Flexível)
        if padrao['std_ent2'] and padrao['std_sai1'] and real_sai1 and real_ent2:
            duracao = padrao['std_ent2'] - padrao['std_sai1']
            limite = real_sai1 + duracao + tolerancia
            if real_ent2 > limite:
                motivos.append(f"Volta Almoço Tardia ({str(real_ent2)[:-3]})")

        # 4. Saída 2 (Saída Antecipada)
        if padrao['std_sai2'] and real_sai2:
            limite = padrao['std_sai2'] - tolerancia
            if real_sai2 < limite:
                motivos.append(f"Saída Antecipada ({str(real_sai2)[:-3]})")

        if len(motivos) > 0:
            qtd = len(motivos)
            total_ocorrencias_geral += qtd
            dias_com_atraso.append({
                'Data': data_val,
                'Dia': chave_dow,
                'Qtd': qtd,
                'Detalhes': ", ".join(motivos)
            })
            
    return nome_funcionario, pd.DataFrame(dias_com_atraso), total_ocorrencias_geral

# Interface Streamlit
st.title("📊 Auditoria de Ponto Detalhada")
st.markdown("Identifica atrasos na entrada, saídas tardias para intervalo e saídas antecipadas.")

arquivo = st.file_uploader("Arraste o arquivo aqui", type=['csv', 'xlsx'])

if arquivo:
    nome, df_res, total = processar_ponto(arquivo)
    if nome:
        st.info(f"Colaborador: **{nome}**")
        c1, c2 = st.columns(2)
        c1.metric("Dias com Ocorrência", len(df_res) if df_res is not None else 0)
        c2.metric("Total de Falhas", total)
        
        if df_res is not None and not df_res.empty:
            st.dataframe(df_res, use_container_width=True, hide_index=True)
        else:
            st.success("Tudo certo! Sem ocorrências.")
