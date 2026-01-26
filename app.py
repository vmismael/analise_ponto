import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from collections import Counter
import re
import io

# --- Configuração da Página ---
st.set_page_config(page_title="Gestão Integrada (RH & Financeiro)", layout="wide")

# ==============================================================================
# FUNÇÃO DE SEGURANÇA (SENHA)
# ==============================================================================
def check_password():
    """Retorna True se o usuário tiver a senha correta."""
    
    def password_entered():
        if st.session_state["password"] == "1406":
            st.session_state["password_correct"] = True
            del st.session_state["password"]
        else:
            st.session_state["password_correct"] = False

    if "password_correct" not in st.session_state:
        st.text_input("🔒 Área Restrita. Digite a senha:", type="password", on_change=password_entered, key="password")
        return False
    elif not st.session_state["password_correct"]:
        st.text_input("🔒 Área Restrita. Digite a senha:", type="password", on_change=password_entered, key="password")
        st.error("😕 Senha incorreta.")
        return False
    else:
        return True

# ==============================================================================
# FUNÇÕES AUXILIARES - GERAIS E PONTO
# ==============================================================================

def limpar_celula_tempo(valor_celula):
    if pd.isna(valor_celula): return None
    s = str(valor_celula).strip()
    # Remove caracteres inválidos, mantém dígitos e :
    s = re.sub(r'[^\d:]', '', s) 
    if not s: return None
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
    if td is None: return ""
    total_segundos = int(td.total_seconds())
    horas = total_segundos // 3600
    minutos = (total_segundos % 3600) // 60
    return f"{horas:02d}:{minutos:02d}"

def processar_ponto(uploaded_file):
    # 1. CARREGAMENTO DO ARQUIVO
    try:
        if uploaded_file.name.endswith('.csv'):
            df = pd.read_csv(uploaded_file, header=None)
        else:
            df = pd.read_excel(uploaded_file, header=None)
    except Exception as e:
        st.error(f"Erro ao ler o arquivo: {e}")
        return None, None, 0

    # 2. LOCALIZAÇÃO DINÂMICA (SCANNER)
    # Procura onde estão as âncoras "SEG" (para horário padrão) e "ENTRADA 1" (para os dados)
    
    markers = {}
    
    # A) Procurar "SEG" (Cabeçalho do Horário Padrão) nas primeiras 30 linhas
    found_seg = False
    for r_idx, row in df.head(30).iterrows():
        for c_idx, val in row.items():
            if str(val).strip().upper() == "SEG":
                markers['seg_row'] = r_idx
                markers['seg_col'] = c_idx
                found_seg = True
                break
        if found_seg: break
        
    if not found_seg:
        st.error("⚠️ Estrutura irreconhecível: Não foi possível encontrar a tabela de Horários (SEG/TER...).")
        return None, None, 0

    # B) Procurar "ENTRADA 1" (Cabeçalho dos Dados)
    found_header = False
    for r_idx, row in df.head(40).iterrows():
        if r_idx < 15: continue 
        for c_idx, val in row.items():
            txt = str(val).strip().upper()
            if "ENTRADA 1" in txt:
                markers['header_row'] = r_idx
                markers['col_ent1_real'] = c_idx
                
                # Procura Saída 1 e Entrada 2 na mesma linha
                for c2_idx in range(c_idx + 1, len(row)):
                    txt2 = str(row[c2_idx]).strip().upper()
                    if "SAÍDA 1" in txt2 or "SAIDA 1" in txt2:
                        markers['col_sai1_real'] = c2_idx
                    if "ENTRADA 2" in txt2:
                        markers['col_ent2_real'] = c2_idx
                found_header = True
                break
        if found_header: break
        
    if 'col_ent1_real' not in markers or 'col_sai1_real' not in markers or 'col_ent2_real' not in markers:
        st.error("⚠️ Estrutura irreconhecível: Não foi possível encontrar as colunas de ENTRADA 1, SAÍDA 1 ou ENTRADA 2.")
        return None, None, 0

    # 3. EXTRAÇÃO DO NOME
    try:
        nome_funcionario = df.iloc[18, 0]
    except:
        nome_funcionario = "Nome não encontrado"

    # 4. MAPEAMENTO DOS HORÁRIOS PADRÃO
    # Usa a coluna do "SEG" encontrada para buscar os outros dias
    col_ref = markers['seg_col']
    agendamento = {}
    dias_sigla = ['SEG', 'TER', 'QUA', 'QUI', 'SEX', 'SAB', 'DOM', 'SÁB']
    
    # Varre a coluna de referência para achar as linhas de cada dia
    for r in range(markers['seg_row'], markers['seg_row'] + 20): # Olha 20 linhas para baixo
        try:
            celula = str(df.iloc[r, col_ref]).strip().upper()
            # Mapeia SEG -> Seg, TER -> Ter...
            dia_chave = None
            if 'SEG' in celula: dia_chave = 'Seg'
            elif 'TER' in celula: dia_chave = 'Ter'
            elif 'QUA' in celula: dia_chave = 'Qua'
            elif 'QUI' in celula: dia_chave = 'Qui'
            elif 'SEX' in celula: dia_chave = 'Sex'
            elif 'SAB' in celula or 'SÁB' in celula: dia_chave = 'Sáb'
            elif 'DOM' in celula: dia_chave = 'Dom'
            
            if dia_chave:
                # Assume que os horários estão deslocados +2, +4, +6 colunas (padrão observado nos dois arquivos)
                ent1 = limpar_celula_tempo(df.iloc[r, col_ref + 2])
                sai1 = limpar_celula_tempo(df.iloc[r, col_ref + 4])
                try: ent2 = limpar_celula_tempo(df.iloc[r, col_ref + 6])
                except: ent2 = None
                
                agendamento[dia_chave] = {'std_ent1': ent1, 'std_sai1': sai1, 'std_ent2': ent2}
        except:
            pass

    # 5. PROCESSAMENTO DAS BATIDAS
    # Começa 3 linhas após o cabeçalho "ENTRADA 1" (Padrão observado: Header -> Vazio -> Totais -> Dados)
    start_row = markers['header_row'] + 3
    linhas_dados = df.iloc[start_row:].copy()
    
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
        
        # Usa as colunas encontradas dinamicamente
        real_ent1 = limpar_celula_tempo(row[markers['col_ent1_real']])
        real_sai1 = limpar_celula_tempo(row[markers['col_sai1_real']])
        real_ent2 = limpar_celula_tempo(row[markers['col_ent2_real']])
        
        motivos = []
        
        # Atraso Entrada Manhã
        if padrao['std_ent1'] and real_ent1:
            limite = padrao['std_ent1'] + tolerancia
            if real_ent1 > limite: 
                motivos.append(f"Manhã ({formatar_visual(real_ent1)})")
        
        # Atraso Volta Almoço
        if padrao['std_ent2'] and padrao['std_sai1'] and real_sai1 and real_ent2:
            duracao = padrao['std_ent2'] - padrao['std_sai1']
            limite = real_sai1 + duracao + tolerancia
            if real_ent2 > limite: 
                motivos.append(f"Volta Almoço (Lim {formatar_visual(limite)} vs Real {formatar_visual(real_ent2)})")

        if motivos:
            qtd = len(motivos)
            total_ocorrencias_geral += qtd
            dias_com_atraso.append({'Data': data_val, 'Dia': chave_dow, 'Qtd': qtd, 'Detalhes': ", ".join(motivos)})
            
    return nome_funcionario, pd.DataFrame(dias_com_atraso), total_ocorrencias_geral

# ==============================================================================
# FUNÇÕES AUXILIARES - FINANCEIRO (DRE)
# ==============================================================================

def limpar_valor_financeiro(valor):
    if pd.isna(valor) or str(valor).strip() == '': return 0.0
    s = str(valor).strip().upper().replace('C', '').replace('D', '')
    s = s.replace('.', '').replace(',', '.')
    try: return float(s)
    except ValueError: return 0.0

def buscar_por_classificacao(df, codigo):
    linha = df[df['Classificação'] == codigo]
    if not linha.empty:
        valor_bruto = linha['Movimento'].values[0]
        return limpar_valor_financeiro(valor_bruto)
    return 0.0

# ==============================================================================
# MENU LATERAL
# ==============================================================================

st.sidebar.title("Navegação")
pagina = st.sidebar.radio("Ir para:", ["📂 Análise de Ponto", "💰 Calc. Vale Alimentação", "💸 Conferência Pix", "📊 Análise DRE"])
st.sidebar.markdown("---")

# ==============================================================================
# PÁGINA 1: ANÁLISE DE PONTO
# ==============================================================================

if pagina == "📂 Análise de Ponto":
    st.title("📂 Análise de Atrasos (Ponto)")
    st.markdown("Faça o upload do arquivo para verificar atrasos na entrada e no almoço.")
    arquivo = st.file_uploader("Carregue o arquivo de Ponto (XLSX ou CSV)", type=['csv', 'xlsx'])

    if arquivo:
        with st.spinner('Analisando estrutura e dados...'):
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
                st.dataframe(df_resultado, use_container_width=True, hide_index=True, column_config={"Qtd": st.column_config.NumberColumn("Qtd", format="%d", width="small")})
            else:
                st.balloons(); st.success("Tudo limpo! Nenhum atraso.")

# ==============================================================================
# PÁGINA 2: CÁLCULO DE VALE ALIMENTAÇÃO
# ==============================================================================

elif pagina == "💰 Calc. Vale Alimentação":
    st.title("💰 Calculadora de Vale Alimentação")
    tabela_cargos = {"Junior": 252.07, "Premium": 348.45, "Senior": 444.84, "Master": 548.64}
    col_input1, col_input2 = st.columns(2)
    with col_input1: cargo_selecionado = st.selectbox("Selecione o Cargo", list(tabela_cargos.keys()))
    valor_inicial_atrasos = st.session_state.get('ultimo_total_atrasos', 0)
    with col_input2: qtd_atrasos = st.number_input("Quantidade Total de Atrasos", min_value=0, value=valor_inicial_atrasos, step=1)
    
    st.divider()
    valor_base_mensal = tabela_cargos[cargo_selecionado]
    valor_diario = valor_base_mensal / 30 
    valor_final = 0.0
    mensagem_penalidade = ""
    cor_alerta = "green"

    if qtd_atrasos < 3:
        valor_final = valor_base_mensal
        mensagem_penalidade = "✅ Nenhuma penalidade aplicada (Menos de 3 atrasos)."
        cor_alerta = "success"
    elif qtd_atrasos == 3:
        desconto = 2 * valor_diario
        valor_final = valor_base_mensal - desconto
        mensagem_penalidade = f"⚠️ Penalidade: Desconto de 2 dias (R$ {desconto:.2f})."
        cor_alerta = "warning"
    elif 4 <= qtd_atrasos <= 7:
        desconto = 7 * valor_diario
        valor_final = valor_base_mensal - desconto
        mensagem_penalidade = f"⛔ Penalidade: Desconto de 7 dias (R$ {desconto:.2f})."
        cor_alerta = "error"
    else:
        valor_final = 148.27
        mensagem_penalidade = "🚨 Penalidade Máxima: Redução para valor fixo de cesta básica."
        cor_alerta = "error"

    st.subheader("Resultado do Cálculo")
    col_res1, col_res2, col_res3 = st.columns(3)
    with col_res1: st.metric("Valor Base (30 dias)", f"R$ {valor_base_mensal:.2f}")
    with col_res2: diferenca = valor_final - valor_base_mensal; st.metric("Desconto / Ajuste", f"R$ {diferenca:.2f}", delta=f"{diferenca:.2f}")
    with col_res3: st.metric("Valor a Receber", f"R$ {valor_final:.2f}")

    if cor_alerta == "success": st.success(mensagem_penalidade)
    elif cor_alerta == "warning": st.warning(mensagem_penalidade)
    else: st.error(mensagem_penalidade)

# ==============================================================================
# PÁGINA 3: CONFERÊNCIA PIX
# ==============================================================================

elif pagina == "💸 Conferência Pix":
    st.title("💸 Conferência de Pix: Excel vs Extrato BB")
    st.markdown("""
    **Instruções:**
    1. Faça upload da Planilha de Pix (.xlsx ou .csv)
    2. Faça upload do Extrato do Banco (.csv)
    3. O sistema irá comparar os valores e indicar a **Linha do Excel** para conferência.
    """)

    # Upload dos arquivos
    uploaded_pix = st.file_uploader("Carregar Planilha Pix (Excel .xlsx ou CSV)", type=["xlsx", "csv"])
    uploaded_bb = st.file_uploader("Carregar Extrato BB (CSV)", type=["csv"])

    if uploaded_pix and uploaded_bb:
        st.divider()
        
        # --- PROCESSAMENTO DA PLANILHA PIX ---
        pix_entries = [] 
        
        try:
            if uploaded_pix.name.endswith('.xlsx'):
                df_pix = pd.read_excel(uploaded_pix, header=None)
            else:
                try:
                    uploaded_pix.seek(0)
                    df_pix = pd.read_csv(uploaded_pix, header=None, sep=None, engine='python')
                except:
                    uploaded_pix.seek(0)
                    df_pix = pd.read_csv(uploaded_pix, header=None, encoding='latin1', sep=None, engine='python')

            if len(df_pix.columns) > 3:
                col_d = df_pix[[2, 3]].dropna()
                for index, row in col_d.iterrows():
                    label = str(row[2]) if pd.notna(row[2]) else ""
                    if "Total" not in label:
                        try:
                            val = float(row[3])
                            pix_entries.append({'valor': val, 'linha': index + 1, 'coluna': 'D'})
                        except:
                            pass
            
            if len(df_pix.columns) > 8:
                col_i = df_pix[[7, 8]].dropna()
                for index, row in col_i.iterrows():
                    label = str(row[7]) if pd.notna(row[7]) else ""
                    if "Total" not in label:
                        try:
                            val = float(row[8])
                            pix_entries.append({'valor': val, 'linha': index + 1, 'coluna': 'I'})
                        except:
                            pass
            
            if not pix_entries:
                st.warning("⚠️ Nenhum valor encontrado na planilha Pix.")
            else:
                st.success(f"✅ Planilha Pix processada: {len(pix_entries)} lançamentos.")
            
        except Exception as e:
            st.error(f"Erro ao ler planilha Pix: {e}")
            st.stop()

        # --- PROCESSAMENTO DO EXTRATO BB ---
        bb_values = []
        try:
            try:
                df_bb = pd.read_csv(uploaded_bb, sep=';', header=None, encoding='latin1')
            except:
                uploaded_bb.seek(0)
                df_bb = pd.read_csv(uploaded_bb, sep=';', header=None, encoding='utf-8')
            
            if len(df_bb.columns) > 10:
                mask = df_bb[9].astype(str).str.contains("Pix-Recebido QR Code", case=False, na=False)
                df_bb_filtered = df_bb[mask]
                
                for val in df_bb_filtered[10]:
                    try:
                        if isinstance(val, str):
                            val = val.replace('.', '').replace(',', '.')
                        bb_values.append(float(val))
                    except:
                        pass
                st.success(f"✅ Extrato BB processado: {len(bb_values)} lançamentos de QR Code.")
            else:
                st.error("❌ Arquivo do Banco inválido.")
                st.stop()
                
        except Exception as e:
            st.error(f"Erro ao ler Extrato BB: {e}")
            st.stop()

        # --- COMPARAÇÃO ---
        if pix_entries and bb_values:
            
            bb_pool = list(bb_values)
            missing_entries = [] 
            matched_entries = [] 
            
            for entry in pix_entries:
                val = entry['valor']
                if val in bb_pool:
                    bb_pool.remove(val)
                    matched_entries.append(entry)
                else:
                    missing_entries.append(entry)
            
            extra_in_bb = bb_pool
            
            st.divider()
            st.subheader("📊 Resultados Detalhados")
            col1, col2, col3 = st.columns(3)
            col1.metric("Confirmados", len(matched_entries))
            col2.metric("Faltam no Banco", len(missing_entries), delta_color="inverse")
            col3.metric("Sobram no Banco", len(extra_in_bb), delta_color="off")
            
            st.markdown("---")
            c1, c2 = st.columns(2)
            
            with c1:
                st.subheader("⚠️ Faltam no Extrato BB")
                st.markdown("**Estão na Planilha (Pix), mas não no Banco.**")
                if missing_entries:
                    df_missing = pd.DataFrame(missing_entries)
                    df_missing = df_missing[['linha', 'coluna', 'valor']]
                    st.dataframe(df_missing.style.format({'valor': 'R$ {:.2f}', 'linha': '{:.0f}'}), height=500, use_container_width=True)
                else:
                    st.info("Nada faltando.")
                    
            with c2:
                st.subheader("❓ Extras no Extrato BB")
                st.markdown("**Estão no Banco, mas não na Planilha.**")
                if extra_in_bb:
                    df_extra = pd.DataFrame(extra_in_bb, columns=["Valor"])
                    st.dataframe(df_extra.style.format("R$ {:.2f}"), height=500, use_container_width=True)
                else:
                    st.success("Nada sobrando.")


# ==============================================================================
# PÁGINA 4: ANÁLISE DRE (PROTEGIDA POR SENHA)
# ==============================================================================

elif pagina == "📊 Análise DRE":
    if not check_password():
        st.stop()
    
    st.sidebar.markdown("### Dados Mês Anterior (DRE)")
    rol_anterior = st.sidebar.number_input("ROL Mês Anterior (R$)", min_value=0.0, value=647538.80, step=1000.0, format="%.2f")
    lucro_anterior = st.sidebar.number_input("Lucro Líq. Mês Anterior (R$)", min_value=0.0, value=228305.24, step=1000.0, format="%.2f")
    
    st.title("📊 Automação de Análise DRE")
    st.markdown("Extração automática de indicadores financeiros via Classificação Contábil.")
    uploaded_file_dre = st.file_uploader("Faça upload do arquivo DRE (CSV ou Excel)", type=['csv', 'xlsx'], key="dre_uploader")

    if uploaded_file_dre is not None:
        try:
            if uploaded_file_dre.name.endswith('.csv'): df_raw = pd.read_csv(uploaded_file_dre, header=None)
            else: df_raw = pd.read_excel(uploaded_file_dre, header=None)

            idx_header = df_raw[df_raw.apply(lambda row: row.astype(str).str.contains('Classificação').any(), axis=1)].index[0]
            df_raw.columns = df_raw.iloc[idx_header]
            df = df_raw[idx_header+1:].reset_index(drop=True)
            df.columns = df.columns.str.strip()
            
            receita_bruta = buscar_por_classificacao(df, '03.1.1')
            deducoes = buscar_por_classificacao(df, '03.1.2')
            custos_servicos = buscar_por_classificacao(df, '04.1')
            lucro_liquido_atual = buscar_por_classificacao(df, '05.1.1.01.001')
            ebitda_valor = buscar_por_classificacao(df, '04.2.9')
            despesas_operacionais = buscar_por_classificacao(df, '04.2')

            rol_atual = receita_bruta - deducoes
            
            if rol_atual and rol_atual != 0:
                margem_bruta = (rol_atual - custos_servicos) / rol_atual
                margem_liquida = lucro_liquido_atual / rol_atual
                margem_ebitda = ebitda_valor / rol_atual
                eficiencia_operacional = despesas_operacionais / rol_atual
            else:
                margem_bruta = 0; margem_liquida = 0; margem_ebitda = 0; eficiencia_operacional = 0

            crescimento_rol = (rol_atual - rol_anterior) / rol_anterior if rol_anterior else 0
            crescimento_lucro = (lucro_liquido_atual - lucro_anterior) / lucro_anterior if lucro_anterior else 0

            st.divider()
            st.subheader("Resultados Consolidados")
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("ROL Atual", f"R$ {rol_atual:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
                st.metric("Lucro Líquido", f"R$ {lucro_liquido_atual:,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.'))
            with col2:
                st.metric("Margem Bruta", f"{margem_bruta:.2%}")
                st.metric("Margem Líquida", f"{margem_liquida:.2%}")
            with col3:
                st.metric("Margem EBITDA", f"{margem_ebitda:.2%}")
                st.metric("Efic. Operacional", f"{eficiencia_operacional:.2%}")
            with col4:
                st.metric("Cresc. ROL", f"{crescimento_rol:.2%}", delta_color="normal")
                st.metric("Cresc. Lucro", f"{crescimento_lucro:.2%}", delta_color="normal")
            st.divider()
            with st.expander("Verificar valores extraídos"):
                st.write(f"**Receita Bruta (03.1.1):** {receita_bruta}")
                st.write(f"**Deduções (03.1.2):** {deducoes}")
                st.write(f"**Custos (04.1):** {custos_servicos}")
                st.write(f"**EBITDA Base (04.2.9):** {ebitda_valor}")
                st.write(f"**Despesas Operacionais (04.2):** {despesas_operacionais}")

        except Exception as e:
            st.error(f"Erro ao processar o arquivo: {e}")
            st.info("Verifique se o arquivo tem as colunas 'Classificação' e 'Movimento'.")
