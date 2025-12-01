import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import re

# Configuração da Página
st.set_page_config(page_title="Analisador de Ponto", layout="wide")

def limpar_celula_tempo(valor_celula):
    """Limpa e converte células do Excel para timedelta."""
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
        
        if 'Sáb' in dow_val or 'Sab' in dow_val:
            chave_dow = 'Sáb'
        elif 'Dom' in dow_val:
            chave_dow = 'Dom'
        else:
            chave_dow = dow_val
            
        if chave_dow not in agendamento or agendamento[chave_dow] is None:
            continue
            
        padrao = agendamento[chave_dow]
        
        real_ent1 = limpar_celula_tempo(row[2]) # Col C
        real_sai1 = limpar_celula_tempo(row[5]) # Col F
        real_ent2 = limpar_celula_tempo(row[8]) # Col I
        
        motivos = []

        # --- Checagem 1: Entrada 1 ---
        if padrao['std_ent1'] and real_ent1:
            limite_ent1 = padrao['std_ent1'] + tolerancia
            if real_ent1 > limite_ent1:
                motivos.append(f"Entrada 1 (Chegou {str(real_ent1)[:-3]})")

        # --- Checagem 2: Entrada 2 (Volta do Almoço) ---
        if padrao['std_ent2'] and padrao['std_sai1'] and real_sai1 and real_ent2:
            duracao_almoco_padrao = padrao['std_ent2'] - padrao['std_sai1']
            limite_ent2 = real_sai1 + duracao_almoco_padrao + tolerancia
            
            if real_ent2 > limite_ent2:
                motivos.append(f"Almoço (Limite {str(limite_ent2)[:-3]} vs Real {str(real_ent2)[:-3]})")
                
        # Se houve algum motivo de atraso nesse dia
        if len(motivos) > 0:
            qtd_dia = len(motivos)
            total_ocorrencias_geral += qtd_dia
            dias_com_atraso.append({
                'Data': data_val,
                'Dia da Semana': chave_dow,
                'Ocorrências': qtd_dia,
                'Detalhes': ", ".join(motivos)
            })
            
    return nome_funcionario, pd.DataFrame(dias_com_atraso), total_ocorrencias_geral

# --- Interface do Streamlit ---

st.title("🕒 Analisador de Atrasos - Cartão Ponto")

arquivo = st.file_uploader("Carregue o arquivo (XLSX ou CSV)", type=['csv', 'xlsx'])

if arquivo:
    with st.spinner('Analisando dados...'):
        nome, df_resultado, total_ocorrencias = processar_ponto(arquivo)
    
    if nome:
        st.success(f"Análise concluída para: **{nome}**")
        
        # Exibindo métricas em colunas
        col1, col2 = st.columns(2)
        
        with col1:
            qtd_dias = len(df_resultado) if df_resultado is not None else 0
            st.metric("Dias com Atraso", qtd_dias, help="Número de dias que tiveram pelo menos 1 atraso")
            
        with col2:
            st.metric("Total de Ocorrências", total_ocorrencias, delta_color="inverse", help="Soma de todos os atrasos (Entrada + Almoço)")
        
        st.divider()
        
        if df_resultado is not None and not df_resultado.empty:
            st.warning(f"Detalhes das {total_ocorrencias} ocorrências encontradas:")
            
            # Formatação da tabela para destacar a quantidade
            st.dataframe(
                df_resultado, 
                use_container_width=True,
                hide_index=True,
                column_config={
                    "Ocorrências": st.column_config.NumberColumn(
                        "Qtd",
                        help="Quantidade de atrasos neste dia",
                        format="%d"
                    )
                }
            )
        else:
            st.balloons()
            st.success("Parabéns! Nenhum atraso encontrado neste período.")
