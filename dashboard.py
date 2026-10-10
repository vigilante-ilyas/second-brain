import streamlit as st
from datetime import date
from repayment_manager import RepaymentManager, RepaymentError

from database import (
    get_all_memories,
    add_memory_to_db,
    update_memory,
    delete_memory,
    MemoryDeletionBlocked
)
from query_router import route_question
from extractor import extract_memory
from voice_dashboard import render_voice_dashboard
from duplicate_checker import find_duplicate, review_duplicates, require_duplicate_approval
from payment_tracker import (
    get_payment_statuses,
    summarize_payments
)


st.set_page_config(
    page_title="Second Brain",
    page_icon="🧠",
    layout="wide"
)


CATEGORIES = [
    "Finance",
    "Health",
    "Home",
    "Education",
    "Work",
    "Family",
    "Identity",
    "Travel",
    "Other"
]


STATUSES = [
    "Pending",
    "Paid",
    "Completed",
    "Planned",
    "Active",
    "Unknown"
]


def render_repayment_history(manager, debt_memory_id):
    st.markdown("**Repayment history**")
    try:
        history = manager.get_repayment_history(debt_memory_id)
    except Exception as error:
        st.error(f"Unable to load repayment history: {error}")
        return
    if not history:
        st.caption("No repayments recorded for this debt.")
        return
    st.dataframe([
        {
            "Payment ID": row["id"],
            "Amount": format_money(row["amount"]),
            "Payment date": row["payment_date"] or "Not provided",
            "Note / source": row["source"] or "Not provided",
            "Recorded at (UTC)": row["created_at"],
        }
        for row in history
    ], hide_index=True, width="stretch")
    st.caption(
        f"Payments for memory #{debt_memory_id}, oldest recorded first. "
        "Histories from duplicate memories are kept separate."
    )


def render_repayment_controls(manager, payment):
    memory_id = payment["memory_id"]
    prefix = f"repayment_{memory_id}_"
    pending_key = prefix + "preview"
    revision_key = prefix + "revision"
    revision = st.session_state.get(revision_key, 0)
    if payment.get("repayment_error"):
        st.warning("Repayment unavailable: " + payment["repayment_error"])
        st.session_state.pop(pending_key, None)
        return
    if payment["amount"] == 0:
        st.success("Fully repaid.")
        st.session_state.pop(pending_key, None)
        return

    with st.form(prefix + "form"):
        mode = st.radio("Repayment type", ["Partial", "Full"], key=prefix + "mode")
        amount_text = st.text_input("Partial amount (whole rupees)", key=prefix + "amount")
        payment_date = st.date_input("Payment date", value=date.today(), key=prefix + "date")
        source = st.text_input("Payment note or source (optional)", key=prefix + "source")
        preview = st.form_submit_button("Preview repayment")

    if preview:
        st.session_state.pop(pending_key, None)
        revision += 1
        st.session_state[revision_key] = revision
        try:
            balance = manager.get_balance(memory_id)
            amount = balance["outstanding_amount"] if mode == "Full" else int(amount_text.strip())
            if amount <= 0 or amount > balance["outstanding_amount"]:
                raise RepaymentError("Enter an amount greater than zero and no larger than the balance.")
            st.session_state[pending_key] = {
                "amount": amount, "payment_date": payment_date.isoformat(),
                "source": source.strip() or None,
                "outstanding": balance["outstanding_amount"],
            }
        except (ValueError, OSError) as error:
            st.error(f"Cannot preview repayment: {error}")

    pending = st.session_state.get(pending_key)
    if pending is None:
        return
    st.info(
        f"Confirm repayment for {payment['person'] or 'Unknown person'} "
        f"(memory #{memory_id}, {payment['direction']}): "
        f"{format_money(pending['amount'])} on {pending['payment_date']}. "
        f"Remaining balance: {format_money(pending['outstanding'] - pending['amount'])}. "
        f"Note/source: {pending['source'] or 'None'}."
    )
    st.caption("This preview stays fixed. Submit a new preview to change the payment details.")
    confirmed = st.checkbox(
        "I confirm this repayment was made and these details are correct.",
        value=False, key=prefix + f"confirm_{revision}",
    )
    if st.button("Save confirmed repayment", disabled=not confirmed,
                 key=prefix + f"save_{revision}"):
        try:
            current = manager.get_balance(memory_id)
            if current["outstanding_amount"] != pending["outstanding"]:
                st.session_state.pop(pending_key, None)
                st.error("The balance changed. Preview the repayment again before confirming.")
                return
            result = manager.record_repayment(
                memory_id, pending["amount"], confirmed=confirmed,
                payment_date=pending["payment_date"], source=pending["source"],
            )
        except Exception as error:
            st.session_state.pop(pending_key, None)
            st.error(f"Repayment was not saved: {error}. Preview again before retrying.")
        else:
            st.session_state.pop(pending_key, None)
            st.session_state[revision_key] = revision + 1
            st.session_state["repayment_message"] = (
                f"Repayment #{result['repayment_id']} saved. "
                f"Remaining balance: {format_money(result['outstanding_amount'])}."
            )
            st.rerun()
    if st.button("Cancel repayment", key=prefix + f"cancel_{revision}"):
        st.session_state.pop(pending_key, None)
        st.session_state[revision_key] = revision + 1
        st.rerun()


def clear_proposal():
    for key in [
        "proposed_memory",
        "raw_information",
        "recorded_date",
        "memory_source",
        "semantic_pending",
        "duplicate_preview_version",
        "duplicate_preview_message"
    ]:
        st.session_state.pop(key, None)


def start_new_review():
    current_version = st.session_state.get(
        "review_version",
        0
    )

    st.session_state["review_version"] = (
        current_version + 1
    )


def format_money(amount):
    return f"Rs. {amount:,.0f}"


def parse_optional_integer(text):
    text = str(text).strip()

    if not text:
        return None

    number = int(
        text.replace(",", "")
    )

    if number < 0:
        raise ValueError(
            "Money amount cannot be negative."
        )

    return number


def parse_optional_float(text):
    text = str(text).strip()

    if not text:
        return None

    return float(text)


st.title("🧠 Second Brain")
st.caption(
    "Your personal AI-powered memory system"
)


tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Ask",
    "Add Memory",
    "Memories",
    "Finances",
    "Voice Note"
])

with tab5:
    render_voice_dashboard()


# ==========================================
# TAB 1: ASK
# ==========================================

with tab1:

    st.subheader("Ask Second Brain")

    question = st.text_input(
        "What would you like to know?",
        placeholder="Example: Who owes me money?",
        key="question"
    )

    if st.button(
        "Ask",
        type="primary"
    ):

        if not question.strip():

            st.warning(
                "Please enter a question."
            )

        else:

            with st.spinner("Thinking..."):

                try:

                    result = route_question(
                        question
                    )

                    st.session_state[
                        "last_answer"
                    ] = result["answer"]

                except Exception as error:

                    st.error(
                        f"Unable to answer: {error}"
                    )

    if "last_answer" in st.session_state:

        st.markdown("### Answer")

        st.text(
            st.session_state[
                "last_answer"
            ]
        )


# ==========================================
# TAB 2: ADD MEMORY
# ==========================================

with tab2:

    st.subheader("Add Memory")

    information = st.text_area(
        "What happened?",
        placeholder=(
            "Example: Fahad borrowed "
            "Rs. 1,200 from me for a taxi."
        ),
        key="memory_information"
    )

    recorded_date = st.text_input(
        "When did you record this?",
        placeholder="Example: 7 Oct 2026",
        key="memory_recorded_date"
    )

    source = st.text_input(
        "Source",
        placeholder="Example: manual_note",
        key="memory_source_input"
    )

    if st.button("Extract Memory"):

        clear_proposal()

        if not information.strip():

            st.warning(
                "Please enter a memory."
            )

        else:

            with st.spinner(
                "Extracting structured information..."
            ):

                try:

                    structured = extract_memory(
                        information
                    )

                    if structured is None:

                        st.error(
                            "I couldn't extract "
                            "the memory safely."
                        )

                    else:

                        start_new_review()

                        st.session_state[
                            "proposed_memory"
                        ] = structured

                        st.session_state[
                            "raw_information"
                        ] = information

                        st.session_state[
                            "recorded_date"
                        ] = recorded_date

                        st.session_state[
                            "memory_source"
                        ] = source

                except Exception as error:

                    st.error(
                        f"Extraction failed: {error}"
                    )

    if "proposed_memory" in st.session_state:

        st.divider()
        st.markdown("### Review Memory")

        proposed = st.session_state[
            "proposed_memory"
        ]

        review_version = st.session_state.get(
            "review_version",
            0
        )

        # Read-only preview of the extracted snapshot, before any save action.
        # Form edits are checked again on submission; approval stays snapshot-bound.
        if st.session_state.get("duplicate_preview_version") != review_version:
            st.session_state.pop("semantic_pending", None)
            st.session_state.pop("duplicate_preview_message", None)
            try:
                preview_memory = {
                    field: (proposed.get(field) or "").strip() or None
                    for field in ("person", "what", "event_date", "location")
                }
                preview_memory.update({
                    "money_amount": parse_optional_integer(
                        "" if proposed.get("money_amount") is None else proposed["money_amount"]),
                    "value": parse_optional_float(
                        "" if proposed.get("value") is None else proposed["value"]),
                    "category": proposed.get("category") if proposed.get("category") in CATEGORIES else "Other",
                    "status": proposed.get("status") if proposed.get("status") in STATUSES else "Unknown",
                })
                preview_memory.update({
                    "information": st.session_state["raw_information"],
                    "date": st.session_state["recorded_date"].strip() or None,
                    "source": st.session_state["memory_source"].strip() or None,
                    "page": None, "file_hash": None, "event_id": None,
                })
                review = review_duplicates(preview_memory)
                if review["exact"]:
                    st.session_state["duplicate_preview_message"] = (
                        f"Exact duplicate of memory #{review['exact']['id']}. Nothing was saved."
                    )
                elif review["candidates"]:
                    revision = st.session_state.get("semantic_revision", 0) + 1
                    st.session_state["semantic_revision"] = revision
                    st.session_state["semantic_pending"] = {
                        "memory": preview_memory, "review": review, "revision": revision,
                    }
            except Exception as error:
                st.session_state["duplicate_preview_message"] = (
                    f"Duplicate preview unavailable: {error}. Saving will require a successful duplicate check."
                )
            st.session_state["duplicate_preview_version"] = review_version

        if st.session_state.get("duplicate_preview_message"):
            st.warning(st.session_state["duplicate_preview_message"])
        if st.session_state.get("semantic_pending"):
            st.warning("Potential duplicates found. Review the candidate IDs and scores below before saving.")

        with st.form(
            f"review_memory_form_{review_version}"
        ):

            person = st.text_input(
                "Person",
                value=(
                    proposed.get("person")
                    or ""
                ),
                key=f"review_person_{review_version}"
            )

            what = st.text_area(
                "What",
                value=(
                    proposed.get("what")
                    or ""
                ),
                key=f"review_what_{review_version}"
            )

            money_amount = st.text_input(
                "Money Amount",
                value=(
                    str(
                        proposed["money_amount"]
                    )
                    if proposed.get(
                        "money_amount"
                    ) is not None
                    else ""
                ),
                key=f"review_money_{review_version}"
            )

            value = st.text_input(
                "Value",
                value=(
                    str(
                        proposed["value"]
                    )
                    if proposed.get(
                        "value"
                    ) is not None
                    else ""
                ),
                key=f"review_value_{review_version}"
            )

            current_category = (
                proposed.get("category")
            )

            if current_category not in CATEGORIES:
                current_category = "Other"

            category = st.selectbox(
                "Category",
                CATEGORIES,
                index=CATEGORIES.index(
                    current_category
                ),
                key=f"review_category_{review_version}"
            )

            current_status = (
                proposed.get("status")
            )

            if current_status not in STATUSES:
                current_status = "Unknown"

            status = st.selectbox(
                "Status",
                STATUSES,
                index=STATUSES.index(
                    current_status
                ),
                key=f"review_status_{review_version}"
            )

            event_date = st.text_input(
                "Event Date",
                value=(
                    proposed.get(
                        "event_date"
                    )
                    or ""
                ),
                key=f"review_event_date_{review_version}"
            )

            location = st.text_input(
                "Location",
                value=(
                    proposed.get(
                        "location"
                    )
                    or ""
                ),
                key=f"review_location_{review_version}"
            )

            st.info(
                "Review all fields carefully. "
                "You can correct AI mistakes "
                "before saving."
            )

            save_clicked = (
                st.form_submit_button(
                    "Save Approved Memory",
                    type="primary"
                )
            )

        if save_clicked:

            st.session_state.pop("semantic_pending", None)
            try:

                parsed_money = (
                    parse_optional_integer(
                        money_amount
                    )
                )

                parsed_value = (
                    parse_optional_float(
                        value
                    )
                )

                new_memory = {
                    "person": (
                        person.strip()
                        or None
                    ),
                    "date": (
                        st.session_state[
                            "recorded_date"
                        ].strip()
                        or None
                    ),
                    "information": (
                        st.session_state[
                            "raw_information"
                        ]
                    ),
                    "source": (
                        st.session_state[
                            "memory_source"
                        ].strip()
                        or None
                    ),
                    "page": None,
                    "file_hash": None,
                    "what": (
                        what.strip()
                        or None
                    ),
                    "money_amount": parsed_money,
                    "value": parsed_value,
                    "category": category,
                    "status": status,
                    "location": (
                        location.strip()
                        or None
                    ),
                    "event_date": (
                        event_date.strip()
                        or None
                    ),
                    "event_id": None
                }

                st.session_state.pop("semantic_pending", None)
                review = review_duplicates(new_memory)
                if review["exact"]:
                    st.warning(
                        f"Exact duplicate of memory #{review['exact']['id']}. Nothing was saved."
                    )
                elif review["candidates"]:
                    st.session_state["semantic_pending"] = {
                        "memory": new_memory, "review": review,
                        "revision": st.session_state.get("semantic_revision", 0) + 1,
                    }
                    st.session_state["semantic_revision"] = st.session_state["semantic_pending"]["revision"]
                else:
                    require_duplicate_approval(review)
                    add_memory_to_db(new_memory)
                    st.success("Memory saved successfully!")
                    clear_proposal()

            except ValueError as error:

                st.error(
                    f"Invalid number: {error}"
                )

            except Exception as error:

                st.error(
                    "Unable to save memory: "
                    f"{error}"
                )


        pending = st.session_state.get("semantic_pending")
        if pending:
            st.warning("Potential duplicates found. Nothing has been saved yet.")
            st.write("**Memory awaiting approval:**", pending["memory"]["information"])
            st.json(pending["memory"])
            st.caption("This approval applies only to the snapshot above. Submit Save Approved Memory to check and apply any field changes.")
            for candidate in pending["review"]["candidates"]:
                match = candidate["memory"]
                with st.expander(f"Memory #{match['id']} - {candidate['reason']} - similarity {candidate['score']:.3f}", expanded=True):
                    st.write(match["information"])
                    st.write({field: match.get(field) for field in
                              ("person", "event_date", "money_amount", "location", "event_id", "source")})
            revision = pending["revision"]
            approved = st.checkbox(
                "I reviewed these matches and explicitly approve saving this memory as an additional record.",
                value=False, key=f"semantic_approval_{review_version}_{revision}",
            )
            if st.button("Save potential duplicate with approval", disabled=not approved,
                         key=f"semantic_save_{review_version}_{revision}"):
                try:
                    fresh_review = review_duplicates(pending["memory"])
                    approved_ids = [item["memory"]["id"] for item in pending["review"]["candidates"]]
                    reviewed_records = {item["memory"]["id"]: item["memory"]
                                        for item in pending["review"]["candidates"]}
                    if any(reviewed_records.get(item["memory"]["id"]) != item["memory"]
                           for item in fresh_review["candidates"]):
                        raise ValueError("Candidate records changed. Review the matches again.")
                    require_duplicate_approval(fresh_review, approved_ids if approved else None)
                    add_memory_to_db(pending["memory"])
                    clear_proposal()
                    st.success("Additional memory saved with your explicit approval.")
                    st.rerun()
                except Exception as error:
                    st.session_state.pop("semantic_pending", None)
                    st.error(f"Nothing was saved: {error}")
                    st.info("Submit Save Approved Memory again to refresh the review.")


# ==========================================
# TAB 3: MEMORIES
# ==========================================

with tab3:

    memories = get_all_memories()

    st.subheader("Memory Dashboard")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Total Memories",
            len(memories)
        )

    with col2:

        people = {
            memory["person"]
            for memory in memories
            if memory.get("person")
        }

        st.metric(
            "People",
            len(people)
        )

    with col3:

        sources = {
            memory["source"]
            for memory in memories
            if memory.get("source")
        }

        st.metric(
            "Stored Sources",
            len(sources)
        )

    st.divider()

    if "memory_message" in st.session_state:

        st.success(
            st.session_state.pop(
                "memory_message"
            )
        )

    search = st.text_input(
        "Search your memories",
        placeholder=(
            "Search by person "
            "or information..."
        ),
        key="memory_search"
    )

    matching_memories = []

    for memory in reversed(memories):

        searchable = (
            str(
                memory.get("person")
                or ""
            )
            + " "
            + str(
                memory.get("information")
                or ""
            )
        ).lower()

        if search.lower() in searchable:
            matching_memories.append(
                memory
            )

    if not matching_memories:

        st.info(
            "No matching memories found."
        )

    for memory in matching_memories:

        memory_id = memory["id"]

        title = (
            memory.get("person")
            or "General Memory"
        )

        with st.expander(
            f"{title} - Memory #{memory_id}"
        ):

            st.write(
                memory["information"]
            )

            st.write(
                "**Recorded date:**",
                memory.get("date")
            )

            st.write(
                "**Event date:**",
                memory.get("event_date")
            )

            st.write(
                "**Category:**",
                memory.get("category")
            )

            st.write(
                "**Status:**",
                memory.get("status")
            )

            st.write(
                "**Source:**",
                memory.get("source")
            )

            st.write(
                "**Page:**",
                memory.get("page")
            )

            st.divider()

            edit_key = (
                f"edit_mode_{memory_id}"
            )

            if st.button(
                "Edit Memory",
                key=f"edit_button_{memory_id}"
            ):
                st.session_state[
                    edit_key
                ] = True

            if st.session_state.get(
                edit_key,
                False
            ):

                st.markdown(
                    "#### Edit Memory"
                )

                with st.form(
                    f"edit_form_{memory_id}"
                ):

                    edit_person = st.text_input(
                        "Person",
                        value=(
                            memory.get("person")
                            or ""
                        ),
                        key=f"edit_person_{memory_id}"
                    )

                    edit_information = st.text_area(
                        "Information",
                        value=(
                            memory.get("information")
                            or ""
                        ),
                        key=f"edit_info_{memory_id}"
                    )

                    edit_what = st.text_area(
                        "What",
                        value=(
                            memory.get("what")
                            or ""
                        ),
                        key=f"edit_what_{memory_id}"
                    )

                    edit_money = st.text_input(
                        "Money Amount",
                        value=(
                            str(
                                memory["money_amount"]
                            )
                            if memory.get(
                                "money_amount"
                            ) is not None
                            else ""
                        ),
                        key=f"edit_money_{memory_id}"
                    )

                    edit_value = st.text_input(
                        "Value",
                        value=(
                            str(memory["value"])
                            if memory.get(
                                "value"
                            ) is not None
                            else ""
                        ),
                        key=f"edit_value_{memory_id}"
                    )

                    current_category = (
                        memory.get("category")
                    )

                    if current_category not in CATEGORIES:
                        current_category = "Other"

                    edit_category = st.selectbox(
                        "Category",
                        CATEGORIES,
                        index=CATEGORIES.index(
                            current_category
                        ),
                        key=f"edit_category_{memory_id}"
                    )

                    current_status = (
                        memory.get("status")
                    )

                    if current_status not in STATUSES:
                        current_status = "Unknown"

                    edit_status = st.selectbox(
                        "Status",
                        STATUSES,
                        index=STATUSES.index(
                            current_status
                        ),
                        key=f"edit_status_{memory_id}"
                    )

                    edit_date = st.text_input(
                        "Recorded Date",
                        value=(
                            memory.get("date")
                            or ""
                        ),
                        key=f"edit_date_{memory_id}"
                    )

                    edit_event_date = st.text_input(
                        "Event Date",
                        value=(
                            memory.get("event_date")
                            or ""
                        ),
                        key=f"edit_event_date_{memory_id}"
                    )

                    edit_location = st.text_input(
                        "Location",
                        value=(
                            memory.get("location")
                            or ""
                        ),
                        key=f"edit_location_{memory_id}"
                    )

                    edit_source = st.text_input(
                        "Source",
                        value=(
                            memory.get("source")
                            or ""
                        ),
                        key=f"edit_source_{memory_id}"
                    )

                    save_changes = (
                        st.form_submit_button(
                            "Save Changes",
                            type="primary"
                        )
                    )

                if save_changes:

                    try:

                        parsed_money = (
                            parse_optional_integer(
                                edit_money
                            )
                        )

                        parsed_value = (
                            parse_optional_float(
                                edit_value
                            )
                        )

                        if not edit_information.strip():
                            raise ValueError(
                                "Information cannot be empty."
                            )

                        duplicate = find_duplicate(
                            edit_information.strip()
                        )

                        if (
                            duplicate
                            and duplicate["id"]
                            != memory_id
                        ):
                            raise ValueError(
                                "Another memory already "
                                "contains this information "
                                f"(Memory #{duplicate['id']})."
                            )

                        updated_memory = {
                            "person": (
                                edit_person.strip()
                                or None
                            ),
                            "date": (
                                edit_date.strip()
                                or None
                            ),
                            "information": (
                                edit_information.strip()
                            ),
                            "source": (
                                edit_source.strip()
                                or None
                            ),
                            "page": memory.get(
                                "page"
                            ),
                            "file_hash": memory.get(
                                "file_hash"
                            ),
                            "what": (
                                edit_what.strip()
                                or None
                            ),
                            "money_amount": (
                                parsed_money
                            ),
                            "value": parsed_value,
                            "category": (
                                edit_category
                            ),
                            "status": edit_status,
                            "location": (
                                edit_location.strip()
                                or None
                            ),
                            "event_date": (
                                edit_event_date.strip()
                                or None
                            ),
                            "event_id": memory.get(
                                "event_id"
                            )
                        }

                        success = update_memory(
                            memory_id,
                            updated_memory
                        )

                        if success:

                            st.session_state[
                                edit_key
                            ] = False

                            st.session_state[
                                "memory_message"
                            ] = (
                                f"Memory #{memory_id} "
                                "updated successfully."
                            )

                            st.rerun()

                        else:

                            st.error(
                                "Memory could not "
                                "be updated."
                            )

                    except ValueError as error:

                        st.error(
                            f"Invalid value: {error}"
                        )

                    except Exception as error:

                        st.error(
                            "Unable to update memory: "
                            f"{error}"
                        )

            st.divider()

            confirm_delete = st.checkbox(
                "I understand this will "
                "permanently delete this memory.",
                key=f"confirm_delete_{memory_id}"
            )

            if st.button(
                "Delete Memory",
                key=f"delete_button_{memory_id}",
                disabled=not confirm_delete
            ):

                try:

                    success = delete_memory(
                        memory_id
                    )

                    if success:

                        st.session_state[
                            "memory_message"
                        ] = (
                            f"Memory #{memory_id} "
                            "deleted successfully."
                        )

                        st.rerun()

                    else:

                        st.error(
                            "Memory could not "
                            "be deleted."
                        )

                except MemoryDeletionBlocked as error:

                    st.warning(str(error))

                except Exception as error:

                    st.error(
                        "Unable to delete memory: "
                        f"{error}"
                    )


# ==========================================
# TAB 4: FINANCES
# ==========================================

with tab4:

    st.subheader(
        "Financial Overview"
    )

    try:

        payments = get_payment_statuses()
        manager = RepaymentManager()
        message = st.session_state.pop("repayment_message", None)
        if message:
            st.success(message)
        for payment in payments:
            payment.setdefault("original_amount", payment["amount"])
            try:
                balance = manager.get_balance(payment["memory_id"])
                payment["amount"] = balance["outstanding_amount"]
                payment["repaid_amount"] = balance["repaid_amount"]
                if balance["fully_repaid"]:
                    payment["payment_status"] = "Fully repaid"
            except RepaymentError as error:
                payment["repayment_error"] = str(error)
                payment["direction"] = "Needs review"

        totals = summarize_payments(
            payments
        )

        owed_to_you = totals.get(
            "Someone owes me",
            0
        )

        you_owe = totals.get(
            "I owe someone",
            0
        )

        needs_review = (
            totals.get("Unknown", 0)
            + totals.get(
                "Needs review",
                0
            )
        )

        upcoming = sum(
            payment["amount"]
            for payment in payments
            if (
                payment["direction"]
                == "Someone owes me"
                and payment[
                    "payment_status"
                ] == "Upcoming"
            )
        )

        col1, col2, col3, col4 = (
            st.columns(4)
        )

        with col1:

            st.metric(
                "Owed to You",
                format_money(
                    owed_to_you
                )
            )

        with col2:

            st.metric(
                "You Owe",
                format_money(
                    you_owe
                )
            )

        with col3:

            st.metric(
                "Needs Review",
                format_money(
                    needs_review
                )
            )

        with col4:

            st.metric(
                "Known Upcoming",
                format_money(
                    upcoming
                )
            )

        st.divider()

        st.markdown(
            "### Payment Records"
        )

        if not payments:

            st.info(
                "No pending financial "
                "records found."
            )

        else:

            for payment in payments:

                person = (
                    payment["person"]
                    or "Unknown person"
                )

                amount = format_money(
                    payment["amount"]
                )

                direction = (
                    payment["direction"]
                )

                due_date = (
                    payment["due_date"]
                    or "Unknown"
                )

                payment_status = (
                    payment["payment_status"]
                )

                with st.expander(
                    f"{person} - {amount} - "
                    f"{payment_status}"
                ):

                    st.write(
                        "**Direction:**",
                        direction
                    )

                    st.write(
                        "**Amount:**",
                        amount
                    )
                    st.write("**Original debt:**", format_money(payment["original_amount"]))
                    if "repaid_amount" in payment:
                        st.write("**Repaid:**", format_money(payment["repaid_amount"]))

                    st.write(
                        "**Due date:**",
                        due_date
                    )

                    st.write(
                        "**Payment status:**",
                        payment_status
                    )

                    st.write(
                        "**Memory ID:**",
                        payment["memory_id"]
                    )
                    render_repayment_history(manager, payment["memory_id"])
                    render_repayment_controls(manager, payment)

        st.caption(
            "Unknown financial directions "
            "require manual review. Dates are "
            "interpreted from stored information; "
            "the dashboard does not change your "
            "original records."
        )

    except Exception as error:

        st.error(
            "Unable to load financial "
            f"dashboard: {error}"
        )
