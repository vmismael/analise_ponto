import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re

# Configuração da Página
st.set_page_config(page_title="Analisador de Ponto", layout="wide")

def limpar_celula_tempo(valor_celula):
    """
    Lê o horário do Excel. 
    IMPORTANTE: Lê segundos se existirem (para não dar erro), 
    mas retornaremos objetos de tempo que podem ser formatados depois.
    """
    if pd.isna(valor_celula):
        return None
    s = str(valor_celula).strip()
    # Mantém apenas números e dois pontos
    s = re.sub(r'[^\d:]', '', s) 
    if not s:
        return None
    try:
        # Tenta formato curto HH:MM
        t = datetime.strptime(s, "%H:%M")
        return timedelta(hours=t.hour, minutes=t.minute)
    except ValueError:
        try:
            # Tenta formato longo HH:MM:SS (necessário para ler seu arquivo corretamente)
            t = datetime.strptime(s, "%H:%M:%S")
            return timedelta(hours=t.hour, minutes=t.minute, seconds=t.second)
        except ValueError:
            return None

def formatar_visual(td):
    """Remove os segundos apenas para a visualização no site (HH:MM)"""
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

    # 1. Obter Nome
    try:
        nome_funcionario = df.iloc[18, 0]
    except:
        nome_funcionario = "Nome não encontrado"

    # 2. Extrair Horários Padrão
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

    # 3. Processar Dados Reais
    linhas_dados = df.iloc[31:].copy()
    dias_com_atraso = []
    total_ocorrencias_geral = 0
    tolerancia = timedelta(minutes=5)

    for idx, row in linhas_dados.iterrows():
        data_str = str(row[0])
        
        if pd.isna(data_str) or '-' not in data_str:
            continue
            
        partes = data_str.split('-')
        if len(partes) < 2:
            continue
        
        data_val = partes[0].strip()
        dow_val = partes[1].strip()
        
        # Normalização do Dia da Semana
        if 'Sáb' in dow_val or 'Sab' in dow_val:
            chave_dow = 'Sáb'
        elif 'Dom' in dow_val:
            chave_dow = 'Dom'
        else:
            chave_dow = dow_val
            
        if chave_dow not in agendamento or agendamento[chave_dow] is None:
            continue
            
        padrao = agendamento[chave_dow]
        
        # Leitura dos horários reais
        real_ent1 = limpar_celula_tempo(row[2]) 
        real_sai1 = limpar_celula_tempo(row[5]) 
        real_ent2 = limpar_celula_tempo(row[8]) 
        
        motivos = []

        # --- REGRA 1: Entrada 1 (Manhã) ---
        if padrao['std_ent1'] and real_ent1:
            limite_ent1 = padrao['std_ent1'] + tolerancia
            if real_ent1 > limite_ent1:
                motivos.append(f"Manhã ({formatar_visual(real_ent1)})")

        # --- REGRA 2: Entrada 2 (Volta do Almoço) ---
        if padrao['std_ent2'] and padrao['std_sai1'] and real_sai1 and real_ent2:
            duracao_almoco_padrao = padrao['std_ent2'] - padrao['std_sai1']
            limite_ent2 = real_sai1 + duracao_almoco_padrao + tolerancia
            
            if real_ent2 > limite_ent2:
                # Mostra o limite permitido vs a hora que chegou
                motivos.append(f"Volta Almoço (Limite {formatar_visual(limite_ent2)} vs Real {formatar_visual(real_ent2)})")
                
        # Se houve ocorrências no dia
        if len(motivos) > 0:
            qtd_dia = len(motivos)
            total_ocorrencias_geral += qtd_dia
            dias_com_atraso.append({
                'Data': data_val,
                'Dia': chave_dow,
                'Qtd': qtd_dia,
                'Detalhes': ", ".join(motivos)
            })
            
    return nome_funcionario, pd.DataFrame(dias_com_atraso), total_ocorrencias_geral

# --- Interface do Streamlit ---

st.title("🕒 Analisador de Chegadas")

arquivo = st.file_uploader("Carregue o arquivo (XLSX ou CSV)", type=['csv', 'xlsx'])

if arquivo:
    with st.spinner('Processando dados...'):
        nome, df_resultado, total_ocorrencias = processar_ponto(arquivo)
    
    if nome:
        st.success(f"Funcionário: **{nome}**")
        
        col1, col2 = st.columns(2)
        
        with col1:
            qtd_dias = len(df_resultado) if df_resultado is not None else 0
            st.metric("Dias com Atraso", qtd_dias)
            
        with col2:
            st.metric("Total de Ocorrências", total_ocorrencias, delta_color="inverse")
        
        st.divider()
        
        if df_resultado is not None and not df_resultado.empty:
            st.warning(f"Lista de Irregularidades ({total_ocorrencias}):")
            
            st.dataframe(
                df_resultado, 
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Qtd": st.column_config.NumberColumn(
                        "Qtd",
                        format="%d",
                        width="small"
                    ),
                    "Detalhes": st.column_config.TextColumn(
                        "Detalhes do Atraso",
                        width="large"
                    )
                }
            )
        else:
            st.balloons()
            st.success("Tudo limpo! Nenhum atraso de chegada detectado.")
