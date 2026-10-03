# utils/htft_dashboard.py
import streamlit as st
import pandas as pd
from utils.htft_scraper import fetch_htft_odds, clear_htft_cache

def show_htft_dashboard():
    """Display the HT/FT Best Bets dashboard."""
    st.markdown("## 🎯 HT/FT Middle Vertical Odds – Best Bets")
    st.caption("Fetches the three middle vertical odds (1/X, X/X, 2/X) and averages them across all leagues.")
    
    if 'htft_data' not in st.session_state:
        st.session_state.htft_data = None
    
    col1, col2 = st.columns([3, 1])
    with col1:
        if st.button("🔄 Fetch HT/FT Odds", type="primary", width="stretch"):
            with st.spinner("Fetching live HT/FT odds from Betpawa..."):
                data = fetch_htft_odds(force_refresh=True)
                if data:
                    st.session_state.htft_data = data
                    st.success(f"✅ Fetched {len(data)} matches")
                else:
                    st.error("❌ No data retrieved.")
    with col2:
        if st.button("🗑️ Clear Cache", type="secondary", width="stretch"):
            clear_htft_cache()
            st.session_state.htft_data = None
            st.toast("🗑️ HT/FT cache cleared!", icon="🗑️")
            st.rerun()
    
    data = st.session_state.htft_data
    if not data:
        st.info("Click the button above to fetch the latest HT/FT odds.")
        return
    
    # Normalize keys (uppercase)
    normalized = []
    for item in data:
        home = item.get('HOME_TEAM') or item.get('home_team') or 'Unknown'
        away = item.get('AWAY_TEAM') or item.get('away_team') or 'Unknown'
        league = item.get('LEAGUE') or item.get('league') or 'Unknown'
        odd_1x = item.get('ODD_1X') or item.get('odd_1x') or 0
        odd_xx = item.get('ODD_XX') or item.get('odd_xx') or 0
        odd_2x = item.get('ODD_2X') or item.get('odd_2x') or 0
        avg = item.get('AVG') or item.get('avg') or (odd_1x + odd_xx + odd_2x) / 3
        normalized.append({
            'HOME_TEAM': home,
            'AWAY_TEAM': away,
            'LEAGUE': league,
            'ODD_1X': odd_1x,
            'ODD_XX': odd_xx,
            'ODD_2X': odd_2x,
            'AVG': avg
        })
    
    sorted_data = sorted(normalized, key=lambda x: x['AVG'], reverse=True)
    best = sorted_data[0]
    
    st.subheader("🏆 Best Bet")
    st.markdown(f"""
    **{best['LEAGUE']}** – {best['HOME_TEAM']} vs {best['AWAY_TEAM']}  
    **Average Odds:** {best['AVG']:.2f}  
    1/X: {best['ODD_1X']:.2f}  |  X/X: {best['ODD_XX']:.2f}  |  2/X: {best['ODD_2X']:.2f}
    """)
    st.divider()
    
    st.subheader("📊 All Matches")
    df = pd.DataFrame(sorted_data)
    df_display = df.copy()
    df_display['AVG'] = df_display['AVG'].map(lambda x: f"{x:.2f}")
    df_display['ODD_1X'] = df_display['ODD_1X'].map(lambda x: f"{x:.2f}")
    df_display['ODD_XX'] = df_display['ODD_XX'].map(lambda x: f"{x:.2f}")
    df_display['ODD_2X'] = df_display['ODD_2X'].map(lambda x: f"{x:.2f}")
    df_display.rename(columns={
        'LEAGUE': 'League',
        'HOME_TEAM': 'Home',
        'AWAY_TEAM': 'Away',
        'AVG': 'Avg',
        'ODD_1X': '1/X',
        'ODD_XX': 'X/X',
        'ODD_2X': '2/X'
    }, inplace=True)
    st.dataframe(df_display, width='stretch')
    
    csv = df_display.to_csv(index=False)
    st.download_button("📥 Download as CSV", data=csv, file_name="htft_best_bets.csv", mime="text/csv", width="stretch")