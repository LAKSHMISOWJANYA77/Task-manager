%%writefile app.py

# app.py
import streamlit as st
from datetime import datetime, date, time, timedelta
import math

# -----------------------
# Helper utilities
# -----------------------
def to_dt(t: time, base_date: date = date.today()):
    """Convert a time to a datetime on base_date. Handles overnight times gracefully."""
    dt = datetime.combine(base_date, t)
    # If the time is for the next day (e.g., 03:00 AM while base_date is today's 10:00 PM), add a day
    if t < time(4, 0) and datetime.now().time() > time(20, 0):
        return dt + timedelta(days=1)
    return dt

def format_range(start_dt: datetime, end_dt: datetime):
    """Formats a datetime range for display."""
    return f"{start_dt.strftime('%I:%M %p')} — {end_dt.strftime('%I:%M %p')}"

def overlap(a_start, a_end, b_start, b_end):
    """Checks if two time intervals overlap."""
    return a_start < b_end and b_start < a_end

def normalize_schedule(tasks):
    """
    Ensures that tasks are sequential and don't overlap by shifting
    the start time of a conflicting task to the end time of the previous one.
    """
    if not tasks:
        return []

    # Sort tasks by start time
    tasks_sorted = sorted(tasks, key=lambda x: x["start_time"])
    fixed = []

    for t in tasks_sorted:
        current_task = t.copy()

        if not fixed:
            fixed.append(current_task)
            continue

        prev = fixed[-1]

        # Check if the current task starts before the previous one ends
        if current_task["start_time"] < prev["end_time"]:
            dur = (current_task["end_time"] - current_task["start_time"])

            # Shift the start time to the end of the previous task
            current_task["start_time"] = prev["end_time"]

            # Calculate the new end time
            current_task["end_time"] = current_task["start_time"] + dur

        fixed.append(current_task)

    return fixed

def detect_conflict(tasks, new_task):
    """Detects if a new task conflicts with any existing task."""
    for t in tasks:
        if overlap(new_task["start_time"], new_task["end_time"], t["start_time"], t["end_time"]):
            return True
    return False

def shift_after_insert(tasks, inserted_index):
    """Shifts all tasks subsequent to the inserted index if they now overlap."""
    tasks = tasks.copy()
    for i in range(inserted_index + 1, len(tasks)):
        prev = tasks[i-1]
        cur = tasks[i]

        if cur["start_time"] < prev["end_time"]:
            dur = cur["end_time"] - cur["start_time"]
            cur["start_time"] = prev["end_time"]
            cur["end_time"] = cur["start_time"] + dur
            tasks[i] = cur

    return tasks

# -----------------------
# Styles (Lightly thicker green: #d6f5d6)
# -----------------------
st.set_page_config(page_title="Life & Career Planner", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background-color: #d6f5d6; }
    .task-card {
        padding: 16px;
        margin: 8px 0;
        border-radius: 12px;
        background: #ffffff;
        box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        font-size: 17px;
    }
    .task-title { font-weight:700; font-size:18px; color: #1a5e22; }
    .task-meta { color:#555; margin-top:6px; font-style: italic; }
    /* Popup style updated to be inline with the task, right under the checkbox */
    .popup-task-complete {
        padding:10px 14px;
        background:#c6f2c6; /* Lighter green for local success */
        border-radius:8px;
        font-size:15px;
        margin-top: -10px; /* Pull it closer to the checkbox */
        margin-bottom:12px;
        font-weight: 600;
        border-left: 5px solid #4CAF50;
    }
    .popup-status {
        padding:14px;
        background:#a2e6a2;
        border-radius:10px;
        font-size:16px;
        margin-bottom:12px;
        font-weight: 600;
        border: 1px solid #7cb97c;
    }
    </style>
    """, unsafe_allow_html=True
)

# -----------------------
# Session defaults
# -----------------------
if "page" not in st.session_state:
    st.session_state.page = "Dashboard"
if "profile_saved" not in st.session_state:
    st.session_state.profile_saved = False
if "profile" not in st.session_state:
    st.session_state.profile = {}
if "template_tasks" not in st.session_state:
    st.session_state.template_tasks = []
if "day_tasks" not in st.session_state:
    st.session_state.day_tasks = []
if "completed" not in st.session_state:
    st.session_state.completed = []
if "holiday_mode" not in st.session_state:
    st.session_state.holiday_mode = False
if "global_message" not in st.session_state: # For general system messages (e.g., saving)
    st.session_state.global_message = ""
if "just_completed_task_index" not in st.session_state: # To control local popup location
    st.session_state.just_completed_task_index = -1
if "last_completion_message" not in st.session_state: # To hold the specific message
    st.session_state.last_completion_message = ""

# -----------------------
# Sidebar (right) navigation
# -----------------------
with st.sidebar:
    st.title("Planner Menu")
    if st.button("🏠 Dashboard"):
        st.session_state.page = "Dashboard"
    if st.button("👤 Profile / Schedule"):
        st.session_state.page = "Profile"
    if st.button("🚀 Career Roadmap"):
        st.session_state.page = "Roadmap"
    if st.button("🧠 Health & Habits"):
        st.session_state.page = "Health"
    st.markdown("---")

    current_holiday_mode = st.session_state.holiday_mode
    holiday = st.checkbox("Holiday Mode (manual day)", value=current_holiday_mode)

    if holiday != current_holiday_mode:
        st.session_state.holiday_mode = holiday
        if holiday:
            st.session_state.day_tasks = []
            st.session_state.global_message = "Holiday Mode enabled. Schedule cleared for manual input."
        else:
            if st.session_state.template_tasks:
                st.session_state.day_tasks = normalize_schedule(st.session_state.template_tasks)
                st.session_state.global_message = "Holiday Mode disabled. Template schedule restored."
            else:
                 st.session_state.global_message = "Holiday Mode disabled. Please set up a Profile template."

# -----------------------
# Profile page: setup
# -----------------------
if st.session_state.page == "Profile":
    st.title("👤 Profile & Daily Template (one-time setup)")
    st.info("Fill this once. This becomes your daily template.")

    name = st.text_input("Full name", value=st.session_state.profile.get("name",""))
    role = st.selectbox("Role", ["Student","Working Professional","Tester","Other"], index=["Student","Working Professional","Tester","Other"].index(st.session_state.profile.get("role", "Student")))

    st.subheader("Work / Study Shift")
    shift_options = ["Morning shift (7–15)","Day shift (9–17)","Night shift (22–06)","Custom"]
    shift_type = st.selectbox("Choose a typical shift", shift_options, index=shift_options.index(st.session_state.profile.get("shift_type", "Day shift (9–17)")))

    default_ws = time(9,0); default_we = time(17,0)
    if shift_type != "Custom":
        if shift_type.startswith("Morning"):
            default_ws = time(7,0); default_we = time(15,0)
        elif shift_type.startswith("Day"):
            default_ws = time(9,0); default_we = time(17,0)
        elif shift_type.startswith("Night"):
            default_ws = time(22,0); default_we = time(6,0)

    work_start = st.time_input("Work / College Start", value=st.session_state.profile.get("work_start", default_ws))
    work_end = st.time_input("Work / College End", value=st.session_state.profile.get("work_end", default_we))
    wake_time = st.time_input("Typical wake up time", value=st.session_state.profile.get("wake_time", time(6,0)))
    sleep_time = st.time_input("Typical sleep time", value=st.session_state.profile.get("sleep_time", time(23,0)))
    st.markdown("---")

    st.subheader("Morning habits (choose order and times)")
    morning_options = ["Reading","Meditation","Jogging/Walking","Watering plants"]
    morning_selected = st.multiselect("Select morning habits (drag to reorder)", morning_options, default=st.session_state.profile.get("morning_habits", []))

    morning_times = st.session_state.profile.get("morning_times", {})
    for h in morning_selected:
        tval = st.time_input(f"Preferred start time for '{h}'", value=morning_times.get(h, wake_time), key=f"m_time_{h}")
        morning_times[h] = tval

    breakfast_time = st.time_input("Breakfast start time", value=st.session_state.profile.get("breakfast_time", time(8,0)))
    st.caption("Breakfast duration: 20 minutes.")

    st.markdown("---")
    st.subheader("Evening habits (choose order and times)")
    evening_options = ["Watering plants","Reading","Light hobbies","Listening to music","Drawing/Painting"]
    evening_selected = st.multiselect("Select evening habits (drag to reorder)", evening_options, default=st.session_state.profile.get("evening_habits", []))

    evening_times = st.session_state.profile.get("evening_times", {})
    for h in evening_selected:
        tval = st.time_input(f"Preferred start time for '{h}'", value=evening_times.get(h, time(19,0)), key=f"e_time_{h}")
        evening_times[h] = tval

    dinner_time = st.time_input("Preferred dinner start time", value=st.session_state.profile.get("dinner_time", time(19,0)))
    st.caption("Dinner duration: 60 minutes.")
    st.markdown("---")

    if st.button("Save Daily Template"):
        profile = {
            "name": name,
            "role": role,
            "work_start": work_start,
            "work_end": work_end,
            "wake_time": wake_time,
            "sleep_time": sleep_time,
            "shift_type": shift_type,
            "morning_habits": morning_selected,
            "morning_times": morning_times,
            "breakfast_time": breakfast_time,
            "evening_habits": evening_selected,
            "evening_times": evening_times,
            "dinner_time": dinner_time
        }
        st.session_state.profile = profile
        st.session_state.profile_saved = True

        # --- Template Tasks Generation ---
        template = []

        # 1. Morning Habits
        for h in profile["morning_habits"]:
            s = to_dt(profile["morning_times"][h])
            dur = 30 if h=="Jogging/Walking" else 20 if h=="Meditation" else 45 if h=="Reading" else 20
            template.append({"title": h, "start_time": s, "end_time": s+timedelta(minutes=dur)})

        # 2. Breakfast (20 mins)
        bstart = to_dt(profile["breakfast_time"])
        template.append({"title":"Breakfast","start_time":bstart,"end_time":bstart+timedelta(minutes=20)})

        # 3. Work / College (main block)
        ws = to_dt(profile["work_start"])
        we = to_dt(profile["work_end"])
        if we <= ws:
            we += timedelta(days=1)

        template.append({"title":"Work / College","start_time":ws,"end_time":we,"meta":{"fixed":True}})

        # 4. Dinner (60 mins)
        dstart = to_dt(profile["dinner_time"])
        template.append({"title":"Dinner","start_time":dstart,"end_time":dstart+timedelta(minutes=60)})

        # 5. Evening Habits
        for h in profile["evening_habits"]:
            s = to_dt(profile["evening_times"][h])
            dur = 45 if h=="Reading" else 30
            template.append({"title": h, "start_time": s, "end_time": s+timedelta(minutes=dur)})

        # Normalize and save to template
        st.session_state.template_tasks = normalize_schedule(template)

        if not st.session_state.holiday_mode:
            st.session_state.day_tasks = st.session_state.template_tasks

        st.session_state.global_message = "Template saved and daily schedule updated (if not in Holiday Mode)."
        st.success(st.session_state.global_message)
        st.session_state.global_message = ""

    if st.button("Back to Dashboard"):
        st.session_state.page = "Dashboard"

# -----------------------
# Dashboard
# -----------------------
elif st.session_state.page == "Dashboard":
    st.title(" Daily Dashboard")
    st.caption(f"Today: {datetime.now().strftime('%A, %d %b %Y')}")

    # Re-normalize day_tasks based on mode and template
    if not st.session_state.holiday_mode and st.session_state.template_tasks:
        template_titles = {t['title'] for t in st.session_state.template_tasks}
        manual_tasks = [t for t in st.session_state.day_tasks if t['title'] not in template_titles or t not in st.session_state.template_tasks]

        full_tasks = [t.copy() for t in st.session_state.template_tasks] + manual_tasks
        st.session_state.day_tasks = normalize_schedule(full_tasks)

    now = datetime.now()

    # Display action messages (non-completion related)
    if st.session_state.global_message:
        st.info(st.session_state.global_message)
        st.session_state.global_message = ""

    # ------------------
    # Timer / Status Update (Ignores completed tasks)
    # ------------------
    next_task = None
    ongoing = None
    tasks_sorted = sorted(st.session_state.day_tasks, key=lambda x: x["start_time"]) if st.session_state.day_tasks else []

    for t in tasks_sorted:
        is_completed = t["title"] in st.session_state.completed

        if t["start_time"] <= now <= t["end_time"] and not is_completed:
            ongoing = t
            break

        if t["start_time"] > now and next_task is None and not is_completed:
            next_task = t

    if ongoing:
        time_left = ongoing["end_time"] - now
        total_seconds = time_left.total_seconds()
        # Use floor for minutes remaining, as ceiling can be misleading when close to 0
        minutes = math.floor(total_seconds / 60)

        status_message = f"🔹 **Ongoing: {ongoing['title']}** "
        if minutes > 1:
            status_message += f"({format_range(ongoing['start_time'], ongoing['end_time'])}). **{minutes} min** remaining."
        elif minutes == 1:
            status_message += f"({format_range(ongoing['start_time'], ongoing['end_time'])}). **1 min** remaining."
        else:
             status_message += f"({format_range(ongoing['start_time'], ongoing['end_time'])}). Ending now."

        st.markdown(f"<div class='popup-status'>{status_message}</div>", unsafe_allow_html=True)
    elif next_task:
        time_to_start = next_task["start_time"] - now
        total_seconds = time_to_start.total_seconds()
        minutes = math.ceil(total_seconds / 60)

        status_message = f"⏰ **Next: {next_task['title']}** at {next_task['start_time'].strftime('%I:%M %p')}. "
        if minutes > 1:
            status_message += f"Starts in **{minutes} min**."
        elif minutes == 1:
            status_message += f"Starts in **1 min**."
        else:
             status_message += "Starting now."

        st.markdown(f"<div class='popup-status'>{status_message}</div>", unsafe_allow_html=True)
    else:
        # Sleep or All Done message
        sleep_dt = to_dt(st.session_state.profile.get("sleep_time", time(23,0)))
        if st.session_state.profile and (now.time() >= sleep_dt.time() or (now.time() < time(4,0) and sleep_dt.time() > time(20,0))):
             st.markdown("<div class='popup-status'>💤 Sleep well! Good night!</div>", unsafe_allow_html=True)
        elif st.session_state.day_tasks and len(st.session_state.completed) == len(st.session_state.day_tasks):
            st.markdown("<div class='popup-status'>🎉 All scheduled tasks are complete for today!</div>", unsafe_allow_html=True)

    st.markdown("---")
    # ------------------
    # Add manual tasks
    # ------------------
    st.subheader("➕ Add a Task (manual)")

    col1, col2, col3 = st.columns([4,2,2])
    with col1: m_title = st.text_input("Task title", key="manual_title")
    with col2: m_start = st.time_input("Start time", key="manual_start", value=now.time())
    with col3: m_dur = st.number_input("Duration (minutes)", min_value=5, max_value=600, value=30, key="manual_dur")

    add_pressed = st.button("Add Task to Day (Check Conflicts)")

    if add_pressed and m_title:
        new_start = to_dt(m_start)
        new_end = new_start + timedelta(minutes=int(m_dur))
        new_task = {"title": m_title, "start_time": new_start, "end_time": new_end}

        target_tasks = st.session_state.day_tasks.copy()
        conflict = detect_conflict(target_tasks, new_task)

        if conflict:
            st.error("Conflict detected with existing schedule!")
            st.markdown("The new task conflicts with another activity. How would you like to proceed?")

            choice = st.radio("Conflict Resolution:",
                              ["1. System: Shift subsequent tasks automatically",
                               "2. User: I will adjust the start time manually and try again"],
                              key="conflict_choice_add")

            if choice.startswith("1."):
                new_list = target_tasks + [new_task]
                new_list = sorted(new_list, key=lambda x: x["start_time"])
                inserted_index = next((i for i, t in enumerate(new_list) if t["title"] == m_title and t["start_time"] == new_start), -1)

                if inserted_index != -1:
                    new_list = shift_after_insert(new_list, inserted_index)
                    st.session_state.day_tasks = normalize_schedule(new_list)
                    st.session_state.global_message = "Task added, and schedule was automatically shifted to resolve conflict."
                    st.rerun()
            else:
                st.info("Please adjust the Start Time and/or Duration above, and press 'Add Task to Day (Check Conflicts)' again.")

        else:
            st.session_state.day_tasks.append(new_task)
            st.session_state.day_tasks = normalize_schedule(st.session_state.day_tasks)
            st.session_state.global_message = "Task added successfully. No conflicts detected."
            st.rerun()

    elif add_pressed and not m_title:
         st.warning("Please enter a title for the task.")

    st.markdown("---")
    # ------------------
    # Display tasks
    # ------------------
    st.subheader("📋 Today's Schedule")
    display_tasks = st.session_state.day_tasks

    if not display_tasks:
        st.info("No tasks for today yet. Add a task above!")
    else:
        remaining = len([t for t in display_tasks if t["title"] not in st.session_state.completed])
        st.write(f"Remaining tasks: **{remaining}** • Total: **{len(display_tasks)}**")

        task_list_placeholder = st.empty()

        with task_list_placeholder.container():
            for i, t in enumerate(display_tasks):
                title = t["title"]
                rng = format_range(t["start_time"], t["end_time"])
                done = title in st.session_state.completed

                # Task card display
                st.markdown(f"<div class='task-card'><div class='task-title'>{title}</div><div class='task-meta'>{rng}</div></div>", unsafe_allow_html=True)

                # Checkbox to mark as done
                ck = st.checkbox(f"Mark done: {title}", value=done, key=f"done_{i}")

                # Update completion status
                if ck and title not in st.session_state.completed:
                    st.session_state.completed.append(title)

                    st.session_state.just_completed_task_index = i

                    # --- START OF CUSTOM MESSAGE LOGIC (THE CHANGE) ---
                    message = f"✅ Task '{title}' completed successfully!"

                    if title == "Work / College":
                        message += " Fantastic work! Your focus period is over. Now, step away from your desk for 10 minutes: Take a **slight walk**, **go out for fresh air**, or **drink a glass of water** to refresh before your next task."

                    elif (t["end_time"] - t["start_time"]).total_seconds() / 60 >= 60:
                        # Generic message for other long tasks (like Reading, Study sessions)
                        message += " Well done on completing a focused block! Take a 5-minute break now."

                    # --- END OF CUSTOM MESSAGE LOGIC ---

                    st.session_state.last_completion_message = message
                    st.rerun()

                elif not ck and title in st.session_state.completed:
                    st.session_state.completed.remove(title)
                    st.session_state.global_message = f"Task '{title}' marked incomplete."
                    st.session_state.just_completed_task_index = -1 # Clear local message marker
                    st.rerun()

                # --- Display completion message right below the task ---
                if i == st.session_state.get("just_completed_task_index", -1):
                    # Check if the task is still marked as completed before displaying the message
                    if title in st.session_state.completed:
                        st.markdown(f"<div class='popup-task-complete'>{st.session_state.last_completion_message}</div>", unsafe_allow_html=True)
                        # Only clear the message marker after display
                        st.session_state.just_completed_task_index = -1
                        st.session_state.last_completion_message = ""

        # All done message (if general status did not cover it)
        if len(st.session_state.completed) == len(display_tasks) and len(display_tasks) > 0 and not ongoing and not next_task:
            st.markdown("<div class='popup-status'>🎉 All tasks finished for today — well done!</div>", unsafe_allow_html=True)

# -----------------------
# Career Roadmap
# -----------------------
elif st.session_state.page == "Roadmap":
    st.title("🚀 Career & Skill Roadmap")
    st.info("Daily and monthly goals lead you to your desired position.")

    role = st.session_state.profile.get("role","Other")
    st.subheader(f"Goal Suggestions for: {role}")

    roadmap = []
    if role=="Student":
        roadmap = [
            "Daily: 30–60 min skill practice (coding, language, etc.)",
            "Weeks 1–4: Master core academic/industry concepts",
            "Months 2–3: Complete intermediate personal projects to apply knowledge",
            "Months 4–6: Work on advanced projects & learn key industry APIs/tools",
            "Final Year / Goal: Secure an Internship & finalize career prep"
        ]
    elif role=="Tester":
        roadmap = [
            "Daily: 1 hour testing practice (manual, exploratory, or automated)",
            "Weeks 1–4: Solidify QA basics and test methodologies (Black Box, White Box)",
            "Months 2–3: Focus on Automation (Selenium/Cypress) and performance tools (JMeter)",
            "Months 4–6: Lead testing for a real-world project and mentor others",
            "Final Goal: Achieve QA Lead or Automation Specialist position"
        ]
    elif role=="Working Professional":
        roadmap = [
            "Daily: 1–2 hours skill enhancement related to next career level",
            "Weeks 1–4: Complete professional growth tasks (certifications, internal training)",
            "Months 2–3: Build portfolio or lead key, high-impact projects at work",
            "Months 4–6: Focus on team management, delegation, and strategic planning skills",
            "Final Goal: Promotion to Team Lead, Manager, or Specialist role"
        ]
    else:
        roadmap = [
            "Daily: 30–60 min dedicated skill practice",
            "Weeks 1–4: Identify and learn key foundational concepts for your field",
            "Months 2–3: Apply acquired skills in small, measurable projects",
            "Months 4–6: Create an impressive portfolio or major personal project",
            "Final Goal: Define and achieve your desired professional position"
        ]

    for step in roadmap:
        st.write("•", step)

    st.markdown("---")
    if st.button("Back to Dashboard"):
        st.session_state.page = "Dashboard"

# -----------------------
# Health page
# -----------------------
elif st.session_state.page == "Health":
    st.title("🧠 Health & Refresh Suggestions")
    st.info("Integrating small breaks helps maintain focus and energy throughout the day.")

    st.subheader("Ideal daily small actions")
    health_actions = [
        "Short morning walk (20–30 min) to boost mood and focus",
        "Stretch breaks (5 min) during every work period (e.g., every 90 min)",
        "Hydration (small sips frequently); keep a water bottle visible",
        "Short breathing breaks (2–5 min) to reset attention",
        "Light reading for pleasure or learning something non-work related"
    ]
    for a in health_actions:
        st.write("✔", a)

    st.markdown("---")
    st.subheader("When tired — quick healthy refresh")
    suggestions = [
        "Take a short 5–10 min walk outside to get sunlight and change scenery",
        "Practice deep breathing (box breathing) for 2 minutes to calm the nervous system",
        "Stretch your shoulders, neck, and back to release muscle tension",
        "Listen to a favorite, energetic song for a quick mood boost"
    ]
    for s in suggestions:
        st.write("🔹", s)

    if st.button("Back to Dashboard"):
        st.session_state.page = "Dashboard"
