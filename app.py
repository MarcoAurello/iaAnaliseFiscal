import streamlit as st
import requests

API_URL = "http://localhost:8000"  # Ajuste conforme o local do seu backend

st.set_page_config(page_title="Análise Tributária de NF", layout="centered")
st.title("🔍 Análise Tributária de Nota Fiscal")

# Seletor de tipo de envio (apenas texto ativo por enquanto)
tipo_envio = st.radio("Como deseja enviar sua nota fiscal?", ["Digitar Texto"])

if tipo_envio == "Digitar Texto":
    st.markdown("Insira abaixo o conteúdo textual da nota fiscal:")
    texto_nf = st.text_area("Conteúdo da Nota Fiscal", height=300)

    pergunta_personalizada = st.text_input("Deseja fazer uma pergunta específica sobre a nota? (opcional)")

    if st.button("🔎 Enviar para Análise"):
        if not texto_nf.strip():
            st.warning("⚠️ O conteúdo da nota fiscal não pode estar vazio.")
        else:
            with st.spinner("⏳ Analisando nota fiscal..."):
                try:
                    payload = {
                        "conteudo": texto_nf
                    }

                    params = {}
                    if pergunta_personalizada.strip():
                        params["pergunta"] = pergunta_personalizada.strip()

                    response = requests.post(f"{API_URL}/upload_nf_texto/", json=payload, params=params)

                    if response.status_code == 200:
                        resultado = response.json()
                        if "error" in resultado:
                            st.error(f"❌ Erro: {resultado['error']}")
                        else:
                            st.success("✅ Nota fiscal analisada com sucesso!")
                            st.markdown("### 🧾 Resumo Tributário da Nota Fiscal:")
                            st.write(resultado.get("resumo_tributario", "Nenhuma informação encontrada."))
                    else:
                        st.error(f"Erro na requisição: Código {response.status_code}")
                except Exception as e:
                    st.error(f"Erro ao conectar com o backend: {e}")
