import streamlit as st
import pandas as pd
import streamlit_authenticator as stauth
from streamlit_gsheets import GSheetsConnection

st.set_page_config(page_title="Bin Inventory App", layout="wide")

# ---------- Helpers for Google Sheets ----------

@st.cache_resource
def get_conn():
    return st.connection("gsheets", type=GSheetsConnection)

def load_sheet(sheet_name: str) -> pd.DataFrame:
    conn = get_conn()
    df = conn.read(worksheet=sheet_name)
    if df is None:
        df = pd.DataFrame()
    df = df.dropna(how="all")
    return df

def write_sheet(sheet_name: str, df: pd.DataFrame):
    conn = get_conn()
    conn.update(worksheet=sheet_name, data=df)

# ---------- Initialization helpers ----------

def init_bins_if_empty():
    bins_df = load_sheet("bins")
    if bins_df.empty:
        data = {
            "bin_id": list(range(1, 11)),
            "bin_name": [f"Bin {i}" for i in range(1, 11)],
        }
        bins_df = pd.DataFrame(data)
        write_sheet("bins", bins_df)

def init_items_if_empty():
    items_df = load_sheet("items")
    if items_df.empty:
        cols = ["item_id", "bin_id", "item_name", "quantity", "category"]
        items_df = pd.DataFrame(columns=cols)
        write_sheet("items", items_df)

def init_users_if_empty():
    users_df = load_sheet("users")
    if users_df.empty:
        # Empty – you should create first admin user manually in sheet.
        # We just ensure columns exist.
        cols = ["username", "name", "password_hash", "role"]
        users_df = pd.DataFrame(columns=cols)
        write_sheet("users", users_df)

# ---------- Authentication ----------

def load_credentials_from_sheet():
    users_df = load_sheet("users")
    if users_df.empty:
        return {"usernames": {}}

    creds = {"usernames": {}}
    for _, row in users_df.iterrows():
        username = str(row["username"])
        creds["usernames"][username] = {
            "name": row["name"],
            "password": row["password_hash"],
            "role": row.get("role", "user"),
        }
    return creds

def get_authenticator():
    credentials = load_credentials_from_sheet()
    authenticator = stauth.Authenticate(
        credentials,
        "bin_app_cookie",
        "bin_app_signature_key",
        cookie_expiry_days=7,
    )
    return authenticator, credentials

# ---------- User management (admin only) ----------

def add_user(username: str, name: str, plain_password: str, role: str):
    users_df = load_sheet("users")
    if "username" not in users_df.columns:
        users_df = pd.DataFrame(columns=["username", "name", "password_hash", "role"])

    if username in users_df["username"].astype(str).tolist():
        st.error("Username already exists")
        return

    hashed_password = stauth.Hasher([plain_password]).generate()[0]
    new_row = {
        "username": username,
        "name": name,
        "password_hash": hashed_password,
        "role": role,
    }
    users_df = pd.concat([users_df, pd.DataFrame([new_row])], ignore_index=True)
    write_sheet("users", users_df)
    st.success(f"User '{username}' added successfully")

def admin_panel():
    st.subheader("Admin Panel - User Management")
    with st.expander("Create new user", expanded=True):
        new_name = st.text_input("Full name")
        new_username = st.text_input("Username")
        new_password = st.text_input("Password", type="password")
        role = st.selectbox("Role", ["user", "admin"])

        if st.button("Create user"):
            if not (new_name and new_username and new_password):
                st.error("All fields are required")
            else:
                add_user(new_username, new_name, new_password, role)

    st.markdown("---")
    st.subheader("Existing users")
    users_df = load_sheet("users")
    if users_df.empty:
        st.info("No users found")
    else:
        st.dataframe(users_df[["username", "name", "role"]])

# ---------- Bins management ----------

def load_bins():
    bins_df = load_sheet("bins")
    if bins_df.empty:
        init_bins_if_empty()
        bins_df = load_sheet("bins")
    bins_df["bin_id"] = bins_df["bin_id"].astype(int)
    return bins_df

def add_bin(bin_name: str):
    bins_df = load_bins()
    if "bin_id" not in bins_df.columns or bins_df.empty:
        next_id = 1
    else:
        next_id = bins_df["bin_id"].max() + 1
    new_row = {"bin_id": next_id, "bin_name": bin_name}
    bins_df = pd.concat([bins_df, pd.DataFrame([new_row])], ignore_index=True)
    write_sheet("bins", bins_df)
    st.success(f"Bin '{bin_name}' added")

def rename_bin(bin_id: int, new_name: str):
    bins_df = load_bins()
    bins_df.loc[bins_df["bin_id"] == bin_id, "bin_name"] = new_name
    write_sheet("bins", bins_df)
    st.success("Bin renamed")

def bins_ui():
    st.subheader("Bins")
    bins_df = load_bins()
    st.dataframe(bins_df, use_container_width=True)

    st.markdown("### Add new bin")
    new_bin_name = st.text_input("New bin name")
    if st.button("Add bin"):
        if new_bin_name.strip():
            add_bin(new_bin_name.strip())
        else:
            st.error("Bin name cannot be empty")

    st.markdown("### Rename existing bin")
    bins_df = load_bins()
    if not bins_df.empty:
        bin_map = {f'{row["bin_name"]} (ID {row["bin_id"]})': row["bin_id"] for _, row in bins_df.iterrows()}
        selected_label = st.selectbox("Select bin to rename", list(bin_map.keys()))
        selected_id = bin_map[selected_label]
        new_name = st.text_input("New name for selected bin")
        if st.button("Rename bin"):
            if new_name.strip():
                rename_bin(selected_id, new_name.strip())
            else:
                st.error("New name cannot be empty")
    else:
        st.info("No bins available")

# ---------- Items management ----------

def load_items():
    items_df = load_sheet("items")
    if items_df.empty:
        init_items_if_empty()
        items_df = load_sheet("items")
    if not items_df.empty:
        items_df["item_id"] = items_df["item_id"].astype(int)
        items_df["bin_id"] = items_df["bin_id"].astype(int)
    return items_df

def add_item(bin_id: int, item_name: str, quantity: str | None, category: str | None):
    items_df = load_items()
    if items_df.empty or "item_id" not in items_df.columns:
        next_id = 1
    else:
        next_id = items_df["item_id"].max() + 1

    new_row = {
        "item_id": next_id,
        "bin_id": bin_id,
        "item_name": item_name,
        "quantity": quantity if quantity else "",
        "category": category if category else "",
    }
    items_df = pd.concat([items_df, pd.DataFrame([new_row])], ignore_index=True)
    write_sheet("items", items_df)
    st.success("Item added")

def items_ui():
    st.subheader("Items")

    bins_df = load_bins()
    if bins_df.empty:
        st.error("No bins available. Please create bins first.")
        return

    items_df = load_items()

    # Add item form
    st.markdown("### Add item to bin")
    bin_map = {f'{row["bin_name"]} (ID {row["bin_id"]})': row["bin_id"] for _, row in bins_df.iterrows()}
    selected_bin_label = st.selectbox("Select bin", list(bin_map.keys()))
    selected_bin_id = bin_map[selected_bin_label]

    item_name = st.text_input("Item name *")
    quantity = st.text_input("Quantity (optional)")
    category = st.text_input("Category (optional)")

    if st.button("Add item"):
        if not item_name.strip():
            st.error("Item name is required")
        else:
            add_item(selected_bin_id, item_name.strip(), quantity.strip(), category.strip())

    st.markdown("### Search items")
    search_query = st.text_input("Search text (item name or category)")
    bin_filter_label = st.selectbox("Filter by bin (optional)", ["All"] + list(bin_map.keys()))
    if st.button("Search"):
        results = search_items(search_query, bins_df, items_df, bin_filter_label if bin_filter_label != "All" else None)
        st.dataframe(results, use_container_width=True)

    st.markdown("### All items")
    merged = merge_items_bins(items_df, bins_df)
    st.dataframe(merged, use_container_width=True)

def merge_items_bins(items_df: pd.DataFrame, bins_df: pd.DataFrame) -> pd.DataFrame:
    if items_df.empty:
        return pd.DataFrame(columns=["item_id", "bin_id", "bin_name", "item_name", "quantity", "category"])
    merged = items_df.merge(bins_df, on="bin_id", how="left")
    merged = merged[["item_id", "bin_id", "bin_name", "item_name", "quantity", "category"]]
    return merged

def search_items(query: str, bins_df: pd.DataFrame, items_df: pd.DataFrame, bin_label: str | None):
    merged = merge_items_bins(items_df, bins_df)
    if merged.empty:
        return merged

    if bin_label:
        # bin_label is "Bin X (ID Y)", extract ID
        bin_id = int(bin_label.split("ID")[-1].strip(" )"))
        merged = merged[merged["bin_id"] == bin_id]

    if query:
        q = query.lower()
        mask = (
            merged["item_name"].astype(str).str.lower().str.contains(q)
            | merged["category"].astype(str).str.lower().str.contains(q)
        )
        merged = merged[mask]

    return merged

# ---------- Main app ----------

def main():
    st.title("Bin Inventory App")

    # Initialize sheets if needed
    init_users_if_empty()
    init_bins_if_empty()
    init_items_if_empty()

    authenticator, credentials = get_authenticator()
    name, auth_status, username = authenticator.login("Login", "main")

    if auth_status is False:
        st.error("Username/password is incorrect")
        return
    elif auth_status is None:
        st.warning("Please enter your username and password")
        return

    # Logged in
    st.sidebar.success(f"Logged in as {name}")
    if st.sidebar.button("Logout"):
        authenticator.logout("Logout", "sidebar")
        st.experimental_rerun()

    user_role = credentials["usernames"][username]["role"]

    # Tabs for UI
    tabs = ["Items", "Bins"]
    if user_role == "admin":
        tabs.append("Admin")

    selected_tab = st.tabs(tabs)

    # Items
    with selected_tab[0]:
        items_ui()

    # Bins
    with selected_tab[1]:
        bins_ui()

    # Admin
    if user_role == "admin":
        with selected_tab[2]:
            admin_panel()

if __name__ == "__main__":
    main()
