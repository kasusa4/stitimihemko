# utils/session_analyzer.py
import pandas as pd
import streamlit as st

def display_session_comparison(session_manager):
    """Display session comparison in Streamlit"""
    if not session_manager.sessions:
        st.info("📊 No sessions available yet. Run some predictions first.")
        return
    
    st.subheader("📊 Session Overview")
    
    # Create dataframe from sessions
    df_data = []
    for s in session_manager.sessions[-10:]:  # show last 10
        global_data = s.get('global', {})
        df_data.append({
            'Session': s['session_id'],
            'Date': s['created_at'][:10],
            'Leagues': len(s.get('leagues', {})),
            'Total Picks': global_data.get('total_predictions', 0),
            'Elite': global_data.get('elite_count', 0),
            'High': global_data.get('high_count', 0),
            'Avg Conf': f"{global_data.get('avg_confidence', 0)*100:.1f}%"
        })
    
    if df_data:
        df = pd.DataFrame(df_data)
        st.dataframe(df, width='stretch')
    
    # Persistent patterns
    patterns = session_manager.compare_sessions()
    if 'message' not in patterns:
        st.subheader("🧠 Persistent Patterns Across Sessions")
        col1, col2 = st.columns(2)
        with col1:
            if patterns.get('over25_teams'):
                st.markdown("**⚽ Over 2.5 Leaders**")
                st.write(", ".join(patterns['over25_teams']))
            if patterns.get('btts_teams'):
                st.markdown("**🧤 BTTS Leaders**")
                st.write(", ".join(patterns['btts_teams']))
        with col2:
            if patterns.get('strong_teams'):
                st.markdown("**🔥 Strong Teams**")
                st.write(", ".join(patterns['strong_teams']))
            if patterns.get('top_picks'):
                st.markdown("**🏆 Persistent Top Picks**")
                st.write(", ".join(patterns['top_picks']))
        
        st.caption(f"Based on {patterns.get('total_sessions', 0)} sessions")
    
    # Session details
    with st.expander("📋 Session Details (Last 5)", expanded=False):
        for session in session_manager.sessions[-5:]:
            st.markdown(f"### Session {session['session_id']} ({session['created_at'][:10]})")
            global_data = session.get('global', {})
            st.metric("Total Predictions", global_data.get('total_predictions', 0))
            
            for league, metrics in session.get('leagues', {}).items():
                st.markdown(f"**{league}**")
                cols = st.columns(4)
                cols[0].metric("Matchdays", metrics.get('matchdays', 0))
                cols[1].metric("Total Matches", metrics.get('total_matches', 0))
                cols[2].metric("Elite", metrics.get('elite_count', 0))
                cols[3].metric("High", metrics.get('high_count', 0))
                
                # Show top predictions
                if metrics.get('predictions'):
                    pred_df = pd.DataFrame(metrics['predictions'])
                    st.dataframe(pred_df, width='stretch')
                st.markdown("---")

def display_session_comparison(session_manager):
    if not session_manager.sessions:
        st.info("📊 No sessions available yet. Run some predictions first.")
        return

    st.subheader("📊 Session Overview")

    # Prepare data for the compact table
    rows = []
    for s in session_manager.sessions[-10:][::-1]:  # newest first
        global_data = s.get('global', {})
        rows.append({
            "Session": s['session_id'],
            "Date": s['created_at'][:10],
            "MD": s.get('matchday', 'N/A'),
            "Picks": global_data.get('total_predictions', 0),
            "Elite": global_data.get('elite_count', 0),
            "High": global_data.get('high_count', 0),
            "Avg Conf": f"{global_data.get('avg_confidence', 0)*100:.1f}%"
        })

    if rows:
        df = pd.DataFrame(rows)
        st.dataframe(df, width='stretch', height=min(300, len(rows)*40 + 40))

        # Persistent patterns (if more than 2 sessions)
        if len(session_manager.sessions) >= 2:
            patterns = session_manager.compare_sessions()
            if 'message' not in patterns:
                with st.expander("🧠 Persistent Patterns Across Sessions"):
                    col1, col2 = st.columns(2)
                    with col1:
                        if patterns.get('over25_teams'):
                            st.markdown("**⚽ Over 2.5 Leaders**")
                            st.write(", ".join(patterns['over25_teams']))
                        if patterns.get('btts_teams'):
                            st.markdown("**🧤 BTTS Leaders**")
                            st.write(", ".join(patterns['btts_teams']))
                    with col2:
                        if patterns.get('strong_teams'):
                            st.markdown("**🔥 Strong Teams**")
                            st.write(", ".join(patterns['strong_teams']))
                        if patterns.get('top_picks'):
                            st.markdown("**🏆 Persistent Top Picks**")
                            st.write(", ".join(patterns['top_picks']))
                    st.caption(f"Based on {patterns.get('total_sessions', 0)} sessions")

        # Session details – small expander per session
        with st.expander("📋 View session predictions"):
            for s in session_manager.sessions[-5:][::-1]:
                st.markdown(f"**Session {s['session_id']}** (MD {s.get('matchday', 'N/A')})")
                preds_by_league = s.get('predictions_by_league', {})
                if preds_by_league:
                    for league, preds in preds_by_league.items():
                        st.caption(f"**{league}**")
                        df_pred = pd.DataFrame(preds)
                        cols = ['Match', 'Top Pick', 'Confidence', 'Most Likely', 'Rating']
                        show_cols = [c for c in cols if c in df_pred.columns]
                        if show_cols:
                            st.dataframe(df_pred[show_cols], width='stretch', height=min(200, len(df_pred)*35+35))
                else:
                    st.caption("No prediction details stored.")

    # DELETE-ALL BUTTON REMOVED – it's now only in the Manage Sessions tab

#def delete_session_and_rerun(session_manager, session_id):
  # session_manager.delete_session(session_id)
  #  st.rerun()