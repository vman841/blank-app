"""
🗑️ SmartBins – Bin Inventory App
Supabase backend | streamlit-authenticator ≥ 0.3
"""

import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from supabase import create_client, Client
from typing import Optional

st.set_page_config(
    page_title="SmartBins",
    page_icon="🗑️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ══════════════════════════════════════════════
#  Supabase client
# ══════════════════════════════════════════════

@st.cache_resource
def get_supabase() -> Client:
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)


# ══════════════════════════════════════════════
#  Generic DB helpers
# ══════════════════════════════════════════════

def fetch_table(table: str) -> pd.DataFrame:
    """Fetch entire table as DataFrame."""
    try:
        sb = get_supabase()
        response = sb.table(table).select("*").execute()
        if not response.data:
            return pd.DataFrame()
        return pd.DataFrame(response.data)
    except Exception as e:
        st.error(f"❌ Failed to read '{table}': {e}")
        return pd.DataFrame()


def insert_row(table: str, row: dict) -> bool:
    """Insert a single row. Returns True on success."""
    try:
        get_supabase().table(table).insert(row).execute()
        return True
    except Exception as e:
        st.error(f"❌ Insert failed on '{table}': {e}")
        return False


def update_row(table: str, match_col: str, match_val, updates: dict) -> bool:
    """Update rows matching match_col = match_val."""
    try:
        get_supabase().table(table).update(updates).eq(match_col, match_val).execute()
        return True
    except Exception as e:
        st.error(f"❌ Update failed on '{table}': {e}")
        return False


def delete_row(table: str, match_col: str, match_val) -> bool:
    """Delete rows matching match_col = match_val."""
    try:
        get_supabase().table(table).delete().eq(match_col, match_val).execute()
        return True
    except Exception as e:
        st.error(f"❌ Delete failed on '{table}': {e}")
        return False


# ══════════════════════════════════════════════
#  Authentication
# ══════════════════════════════════════════════

def build_credentials() -> dict:
    """
    Load users from Supabase and build the credentials dict
    expected by streamlit-authenticator ≥ 0.3.
    Passwords are plain text in DB; auto_hash=True hashes them in memory.
    """
    users_df = fetch_table("users")

    if users_df.empty or "username" not in users_df.columns:
        return {"usernames": {}}

    for col, default in [("name", ""), ("email", ""), ("role", "user")]:
        if col not in users_df.columns:
            users_df[col] = default

    users_df = (
        users_df
        .dropna(subset=["username", "password"])
        .pipe(lambda d: d[d["username"].astype(str).str.strip() != ""])
        .pipe(lambda d: d[d["password"].astype(str).str.strip() != ""])
    )

    creds = {"usernames": {}}
    for _, row in users_df.iterrows():
        username = str(row["username"]).strip()
        name     = str(row.get("name", username)).strip() or username
        parts    = name.split(" ", 1)
        creds["usernames"][username] = {
            "email":      str(row.get("email", f"{username}@example.com")).strip(),
            "first_name": parts[0],
            "last_name":  parts[1] if len(parts) > 1 else "",
            "password":   str(row["password"]).strip(),
            "roles":      [str(row.get("role", "user")).strip() or "user"],
        }
    return creds


def get_authenticator():
    credentials = build_credentials()
    authenticator = stauth.Authenticate(
        credentials,
        cookie_name="bin_app_cookie",
        cookie_key="bin_app_s3cur3_k3y_2025",
        cookie_expiry_days=7,
        auto_hash=True,   # plain text passwords hashed in memory on every run
    )
    return authenticator, credentials


# ══════════════════════════════════════════════
#  Admin panel
# ══════════════════════════════════════════════

def admin_panel():
    st.subheader("🔧 Admin – User Management")

    with st.expander("➕ Create new user", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            new_username = st.text_input("Username",         key="adm_username")
            new_name     = st.text_input("Full name",        key="adm_name")
            new_email    = st.text_input("Email (optional)", key="adm_email")
        with col2:
            new_password = st.text_input("Password", type="password", key="adm_password")
            role         = st.selectbox("Role", ["user", "admin"],    key="adm_role")

        if st.button("Create user", use_container_width=True, key="adm_create_btn"):
            if not (new_username.strip() and new_name.strip() and new_password.strip()):
                st.error("❌ Username, full name, and password are required")
                return

            users_df = fetch_table("users")
            if (not users_df.empty
                    and "username" in users_df.columns
                    and new_username.strip() in users_df["username"].astype(str).values):
                st.error("❌ Username already exists")
                return

            ok = insert_row("users", {
                "username": new_username.strip(),
                "name":     new_name.strip(),
                "email":    new_email.strip() or f"{new_username.strip()}@example.com",
                "password": new_password,      # plain text; auto_hash=True handles it
                "role":     role,
            })
            if ok:
                st.success(f"✅ User '{new_username.strip()}' created!")
                st.rerun()

    with st.expander("🗑️ Delete user", expanded=False):
        users_df = fetch_table("users")
        current_user = st.session_state.get("username", "")
        if not users_df.empty and "username" in users_df.columns:
            deletable = [u for u in users_df["username"].astype(str).tolist()
                         if u != current_user]
            if deletable:
                del_user = st.selectbox("Select user to delete", deletable, key="adm_del_user")
                if st.button("Delete user", use_container_width=True, key="adm_del_btn"):
                    if delete_row("users", "username", del_user):
                        st.success(f"✅ User '{del_user}' deleted!")
                        st.rerun()
            else:
                st.info("No other users to delete.")

    users_df = fetch_table("users")
    if not users_df.empty:
        st.subheader("👥 Existing Users")
        display_cols = [c for c in ["username", "name", "email", "role"] if c in users_df.columns]
        st.dataframe(users_df[display_cols], use_container_width=True)


# ══════════════════════════════════════════════
#  Bins
# ══════════════════════════════════════════════

def load_bins() -> pd.DataFrame:
    df = fetch_table("bins")
    if df.empty or "bin_id" not in df.columns:
        return pd.DataFrame(columns=["bin_id", "bin_name"])
    df["bin_id"] = pd.to_numeric(df["bin_id"], errors="coerce")
    return df.dropna(subset=["bin_id"]).sort_values("bin_id").reset_index(drop=True)


def bins_ui():
    st.subheader("🗂️ Bins Management")
    bins_df = load_bins()
    st.dataframe(bins_df, use_container_width=True)

    st.markdown("### ➕ Add New Bin")
    new_bin_name = st.text_input("Bin name", key="bins_add_name")
    if st.button("Add bin", use_container_width=True, key="bins_add_btn"):
        if new_bin_name.strip():
            # bin_id is SERIAL — Postgres auto-assigns it
            if insert_row("bins", {"bin_name": new_bin_name.strip()}):
                st.success("✅ Bin added!")
                st.rerun()
        else:
            st.error("❌ Bin name required")

    st.markdown("### ✏️ Rename Bin")
    bins_df = load_bins()
    if not bins_df.empty:
        bin_options = {
            f"{row['bin_name']} (ID:{int(row['bin_id'])})": int(row["bin_id"])
            for _, row in bins_df.iterrows()
        }
        selected = st.selectbox("Select bin", list(bin_options.keys()), key="bins_rename_sel")
        new_name = st.text_input("New name", key="bins_rename_name")
        if st.button("Rename", use_container_width=True, key="bins_rename_btn"):
            if new_name.strip():
                if update_row("bins", "bin_id", bin_options[selected], {"bin_name": new_name.strip()}):
                    st.success("✅ Bin renamed!")
                    st.rerun()
            else:
                st.error("❌ New name required")

    st.markdown("### 🗑️ Delete Bin")
    if not bins_df.empty:
        del_options = {
            f"{row['bin_name']} (ID:{int(row['bin_id'])})": int(row["bin_id"])
            for _, row in bins_df.iterrows()
        }
        del_selected = st.selectbox("Select bin to delete", list(del_options.keys()), key="bins_del_sel")
        st.caption("⚠️ All items in this bin will also be deleted (cascade).")
        if st.button("Delete bin", use_container_width=True, key="bins_del_btn"):
            if delete_row("bins", "bin_id", del_options[del_selected]):
                st.success("✅ Bin deleted!")
                st.rerun()


# ══════════════════════════════════════════════
#  Items
# ══════════════════════════════════════════════

def load_items() -> pd.DataFrame:
    df = fetch_table("items")
    if df.empty or "item_id" not in df.columns:
        return pd.DataFrame(columns=["item_id", "bin_id", "item_name", "quantity", "category"])
    df["item_id"] = pd.to_numeric(df["item_id"], errors="coerce")
    df["bin_id"]  = pd.to_numeric(df["bin_id"],  errors="coerce")
    return df.dropna(subset=["item_id", "bin_id"]).sort_values("item_id").reset_index(drop=True)


def search_items(query: str, bin_filter_id: Optional[int]) -> pd.DataFrame:
    items_df = load_items()
    bins_df  = load_bins()
    empty_cols = ["item_id", "bin_id", "bin_name", "item_name", "quantity", "category"]

    if items_df.empty:
        return pd.DataFrame(columns=empty_cols)

    merged = items_df.merge(bins_df, on="bin_id", how="left")

    if bin_filter_id is not None:
        merged = merged[merged["bin_id"] == bin_filter_id]

    if query.strip():
        mask = (
            merged["item_name"].astype(str).str.contains(query, case=False, na=False) |
            merged["category"].astype(str).str.contains(query, case=False, na=False)
        )
        merged = merged[mask]

    cols = [c for c in empty_cols if c in merged.columns]
    return merged[cols].reset_index(drop=True)


def items_ui():
    st.subheader("📦 Items Management")
    bins_df = load_bins()

    if bins_df.empty:
        st.error("❌ No bins found – go to the Bins tab and create some first.")
        return

    bin_options = {row["bin_name"]: int(row["bin_id"]) for _, row in bins_df.iterrows()}

    st.markdown("### ➕ Add New Item")
    col1, col2 = st.columns([1, 2])
    with col1:
        selected_bin    = st.selectbox("Select bin", list(bin_options.keys()), key="items_add_bin")
        selected_bin_id = bin_options[selected_bin]
    with col2:
        item_name = st.text_input("Item name *",         key="items_add_name")
        quantity  = st.text_input("Quantity (optional)", key="items_add_qty")
        category  = st.text_input("Category (optional)", key="items_add_cat")

    if st.button("➕ Add item", use_container_width=True, key="items_add_btn"):
        if item_name.strip():
            # item_id is SERIAL — Postgres auto-assigns it
            if insert_row("items", {
                "bin_id":    selected_bin_id,
                "item_name": item_name.strip(),
                "quantity":  quantity.strip(),
                "category":  category.strip(),
            }):
                st.success("✅ Item added!")
                st.rerun()
        else:
            st.error("❌ Item name is required")

    st.markdown("### 🔍 Search Items")
    col1, col2 = st.columns(2)
    with col1:
        search_query = st.text_input("Search by name or category", key="items_search_q")
    with col2:
        filter_opts     = {"All bins": None, **bin_options}
        bin_filter_name = st.selectbox("Filter by bin", list(filter_opts.keys()), key="items_filter_bin")
        bin_filter_id   = filter_opts[bin_filter_name]

    st.markdown("### 📋 All Items")
    results = search_items(search_query, bin_filter_id)
    st.dataframe(results, use_container_width=True)

    st.markdown("### 🗑️ Delete Item")
    if not results.empty and "item_id" in results.columns:
        item_del_options = {
            f"[ID:{int(r['item_id'])}] {r['item_name']} → {r.get('bin_name','')}": int(r["item_id"])
            for _, r in results.iterrows()
        }
        del_item = st.selectbox("Select item to delete", list(item_del_options.keys()), key="items_del_sel")
        if st.button("Delete item", use_container_width=True, key="items_del_btn"):
            if delete_row("items", "item_id", item_del_options[del_item]):
                st.success("✅ Item deleted!")
                st.rerun()


# ══════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════

def main():
    st.title("🗑️ Bin Inventory App")

    # ── Login ──
    authenticator, credentials = get_authenticator()

    try:
        authenticator.login(location="main")
    except Exception as e:
        st.error(f"Login widget error: {e}")
        return

    auth_status = st.session_state.get("authentication_status")
    name        = st.session_state.get("name", "User")
    username    = st.session_state.get("username", "")

    if auth_status is False:
        st.error("❌ Incorrect username or password")
        return
    elif auth_status is None:
        st.info("👤 Please enter your credentials to log in")
        return

    # ── Authenticated ──
    user_data = credentials.get("usernames", {}).get(username, {})
    roles     = user_data.get("roles", ["user"])
    user_role = roles[0] if roles else "user"

    with st.sidebar:
        st.success(f"👋 {name}")
        st.caption(f"Role: **{user_role}**")
        if st.button("🚪 Logout", use_container_width=True, key="logout_btn"):
            authenticator.logout(location="unrendered")
            st.rerun()

    # ── Tabs ──
    tab_labels = ["📦 Items", "🗂️ Bins"]
    if user_role == "admin":
        tab_labels.append("🔧 Admin")

    tabs = st.tabs(tab_labels)

    with tabs[0]:
        items_ui()
    with tabs[1]:
        bins_ui()
    if user_role == "admin" and len(tabs) == 3:
        with tabs[2]:
            admin_panel()


if __name__ == "__main__":
    main()
