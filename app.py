import customtkinter as ctk
from PIL import Image
from tkinter import filedialog, messagebox, simpledialog
import cv2
from ultralytics import YOLO
import time
import os
import winsound
import numpy as np
from collections import deque

# ======================================
# APP SETTINGS
# ======================================

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

# ======================================
# MAIN WINDOW
# ======================================

app = ctk.CTk()
app.title("CRMS - Fixed Desk Seating with Absents Logging")
app.geometry("1400x800")

# ======================================
# CAMERA
# ======================================

current_camera_source = 0
cap = cv2.VideoCapture(current_camera_source)
running = True

# ======================================
# FOLDERS
# ======================================

if not os.path.exists("screenshots"):
    os.makedirs("screenshots")
if not os.path.exists("recordings"):
    os.makedirs("recordings")

# ======================================
# LOAD YOLO MODEL
# ======================================

model = YOLO("yolov8s.pt")

# ======================================
# SEAT MATRIX – editable (set your own roll numbers)
# ======================================

seat_ids = [
    ["S1", "S2", "S3"],
    ["S4", "S5", "S6"],
    ["S7", "S8", "S9"],
    ["S10", "S11", "S12"]
]

# ======================================
# STUDENT STATE
# ======================================

student_states = {}

# ======================================
# OBJECT TRACKING (for phones)
# ======================================

phone_tracker = {}
next_phone_id = 0

# ======================================
# VIDEO RECORDING BUFFER
# ======================================

FRAME_BUFFER_SIZE = 150
RECORD_SECONDS = 10
frame_buffer = deque(maxlen=FRAME_BUFFER_SIZE)
is_recording = False
video_writer = None
recording_start_time = 0
recording_filename = ""

# ======================================
# UI ALERT STATE
# ======================================

alert_active = False
alert_start_time = 0
alert_popup = None

# ======================================
# Frame counter for skipping
# ======================================
frame_counter = 0
last_processed_frame = None

# ======================================
# SHOW ABSENTS FLAG AND LIST
# ======================================
show_absent = False
current_absent_list = []

# ======================================
# TOP BAR
# ======================================

topbar = ctk.CTkFrame(app, height=70, corner_radius=0)
topbar.pack(fill="x")

camera_label = ctk.CTkLabel(
    topbar,
    text="CAMERA 01",
    font=("Arial", 22, "bold")
)
camera_label.pack(side="left", padx=30, pady=20)

live_label = ctk.CTkLabel(
    topbar,
    text="● LIVE",
    font=("Arial", 20, "bold"),
    text_color="#00ff99"
)
live_label.pack(side="left", padx=20)

student_count = ctk.CTkLabel(
    topbar,
    text="Students : 0",
    font=("Arial", 18, "bold")
)
student_count.pack(side="right", padx=20)

suspicious_count_label = ctk.CTkLabel(
    topbar,
    text="Suspicious : 0",
    font=("Arial", 18, "bold"),
    text_color="red"
)
suspicious_count_label.pack(side="right", padx=20)

# ======================================
# CAMERA SELECTION DROPDOWN
# ======================================

def change_camera(choice):
    global cap, current_camera_source
    if cap is not None:
        cap.release()
    if choice == "Custom URL...":
        url = simpledialog.askstring("Enter RTSP URL", "Enter the RTSP stream URL (e.g., rtsp://192.168.1.100:554/stream):")
        if url:
            current_camera_source = url
        else:
            current_camera_source = 0
    else:
        try:
            current_camera_source = int(choice)
        except:
            current_camera_source = 0
    cap = cv2.VideoCapture(current_camera_source)
    if not cap.isOpened():
        messagebox.showerror("Camera Error", f"Failed to open camera: {current_camera_source}")
        cap = cv2.VideoCapture(0)
        current_camera_source = 0
    camera_label.configure(text=f"CAMERA: {current_camera_source}")

camera_options = ["0", "1", "2", "3", "4", "Custom URL..."]
camera_menu = ctk.CTkOptionMenu(
    topbar,
    values=camera_options,
    command=change_camera,
    width=120,
    font=("Arial", 16)
)
camera_menu.set("0")
camera_menu.pack(side="left", padx=10)

# ======================================
# CONFIGURE SEATS BUTTON
# ======================================

def configure_seats():
    global seat_ids
    config_win = ctk.CTkToplevel(app)
    config_win.title("Configure Roll Numbers")
    config_win.geometry("500x400")
    config_win.attributes("-topmost", True)
    config_win.grab_set()

    grid_frame = ctk.CTkFrame(config_win)
    grid_frame.pack(padx=20, pady=20, fill="both", expand=True)

    entries = []
    for i, row in enumerate(seat_ids):
        for j, val in enumerate(row):
            label = ctk.CTkLabel(grid_frame, text=f"Seat {i+1}-{j+1}:", font=("Arial", 14))
            label.grid(row=i, column=j*2, padx=5, pady=5, sticky="e")
            entry = ctk.CTkEntry(grid_frame, width=80, font=("Arial", 14))
            entry.insert(0, val)
            entry.grid(row=i, column=j*2+1, padx=5, pady=5, sticky="w")
            entries.append((i, j, entry))

    def save_changes():
        for i, j, entry in entries:
            seat_ids[i][j] = entry.get().strip()
        config_win.destroy()
        add_log("Roll numbers updated")

    btn_frame = ctk.CTkFrame(config_win, fg_color="transparent")
    btn_frame.pack(pady=10)

    save_btn = ctk.CTkButton(btn_frame, text="💾 Save", command=save_changes, width=120)
    save_btn.pack(side="left", padx=10)

    cancel_btn = ctk.CTkButton(btn_frame, text="Cancel", command=config_win.destroy, width=120, fg_color="gray")
    cancel_btn.pack(side="left", padx=10)

config_button = ctk.CTkButton(
    topbar,
    text="⚙️ Configure Seats",
    width=140,
    command=configure_seats
)
config_button.pack(side="left", padx=10)

# ======================================
# SHOW ABSENTS BUTTON
# ======================================

def toggle_absents():
    global show_absent, current_absent_list
    show_absent = not show_absent
    if show_absent:
        if current_absent_list:
            add_log(f"Absents : total {len(current_absent_list)}")
            for sid in current_absent_list:
                add_log(f"  Student {sid}")
        else:
            add_log("No absent students.")
    else:
        add_log("Absents hidden")

absents_button = ctk.CTkButton(
    topbar,
    text="👤 Show Absents",
    width=140,
    command=toggle_absents,
    fg_color="orange",
    hover_color="darkorange"
)
absents_button.pack(side="left", padx=10)

# ======================================
# BUTTONS
# ======================================

start_button = ctk.CTkButton(
    topbar,
    text="▶ START",
    fg_color="green",
    hover_color="darkgreen",
    width=120,
    command=lambda: start_camera()
)
start_button.pack(side="right", padx=10)

stop_button = ctk.CTkButton(
    topbar,
    text="⏹ STOP",
    fg_color="red",
    hover_color="darkred",
    width=120,
    command=lambda: stop_camera()
)
stop_button.pack(side="right", padx=10)

upload_button = ctk.CTkButton(
    topbar,
    text="🖼 Upload Image",
    width=140,
    command=lambda: upload_image()
)
upload_button.pack(side="right", padx=10)

# ======================================
# MAIN CONTAINER
# ======================================

main_container = ctk.CTkFrame(app, fg_color="transparent")
main_container.pack(fill="both", expand=True, padx=15, pady=15)

# ======================================
# VIDEO FRAME
# ======================================

video_frame = ctk.CTkFrame(
    main_container,
    corner_radius=15,
    border_width=0,
    border_color="red"
)
video_frame.pack(side="left", fill="both", expand=True, padx=(0, 15))

camera_display = ctk.CTkLabel(video_frame, text="CAMERA")
camera_display.pack(fill="both", expand=True, padx=10, pady=10)

# ======================================
# LOGS FRAME
# ======================================

logs_frame = ctk.CTkFrame(main_container, width=300, corner_radius=15)
logs_frame.pack(side="right", fill="y")

logs_title = ctk.CTkLabel(logs_frame, text="ACTIVITY LOGS", font=("Arial", 22, "bold"))
logs_title.pack(pady=20)

logs_box = ctk.CTkTextbox(logs_frame, width=280, height=600, font=("Arial", 16))
logs_box.pack(padx=10, pady=10, fill="both", expand=True)

# ======================================
# LOG FUNCTION
# ======================================

def add_log(message):
    current_time = time.strftime("%H:%M:%S")
    logs_box.insert("0.0", f"[{current_time}] {message}\n")

# ======================================
# ALERT SOUND
# ======================================

def show_alert():
    winsound.Beep(1200, 200)

# ======================================
# START / STOP CAMERA
# ======================================

def start_camera():
    global running
    running = True
    add_log("Monitoring Started")

def stop_camera():
    global running
    running = False
    add_log("Monitoring Stopped")

# ======================================
# UI ALERT FUNCTIONS
# ======================================

def show_alert_popup(student_id, event_type):
    global alert_popup
    if alert_popup is not None and alert_popup.winfo_exists():
        alert_popup.destroy()
        alert_popup = None

    alert_popup = ctk.CTkToplevel(app)
    alert_popup.title("⚠️ ALERT")
    alert_popup.geometry("400x150")
    alert_popup.attributes("-topmost", True)
    alert_popup.after(2000, alert_popup.destroy)

    app_x = app.winfo_x()
    app_y = app.winfo_y()
    app_w = app.winfo_width()
    app_h = app.winfo_height()
    pop_x = app_x + app_w//2 - 200
    pop_y = app_y + app_h//2 - 75
    alert_popup.geometry(f"400x150+{pop_x}+{pop_y}")

    label = ctk.CTkLabel(
        alert_popup,
        text=f"🚨 SUSPICIOUS ACTIVITY!\nStudent: {student_id}\nEvent: {event_type}",
        font=("Arial", 20, "bold"),
        text_color="red"
    )
    label.pack(expand=True, padx=20, pady=20)

def trigger_alert(student_id, event_type, frame):
    global alert_active, alert_start_time

    add_log(f"{student_id} {event_type}")
    show_alert()
    filename = f"screenshots/{student_id}_{int(time.time())}.jpg"
    cv2.imwrite(filename, frame)
    start_recording(student_id, frame)

    alert_active = True
    alert_start_time = time.time()
    video_frame.configure(border_width=5, border_color="red")
    show_alert_popup(student_id, event_type)

# ======================================
# VIDEO RECORDING FUNCTIONS
# ======================================

def start_recording(student_id, current_frame):
    global is_recording, video_writer, recording_start_time, recording_filename
    if is_recording:
        return

    timestamp = int(time.time())
    recording_filename = f"recordings/{student_id}_{timestamp}.avi"
    fourcc = cv2.VideoWriter_fourcc(*'XVID')
    h, w = current_frame.shape[:2]
    video_writer = cv2.VideoWriter(recording_filename, fourcc, 30.0, (w, h))
    if video_writer is None:
        add_log("Failed to create video writer")
        return

    for buf_frame in frame_buffer:
        video_writer.write(buf_frame)
    video_writer.write(current_frame)

    is_recording = True
    recording_start_time = time.time()
    add_log(f"Recording started for {student_id}")

def stop_recording():
    global is_recording, video_writer, recording_filename
    if video_writer is not None:
        video_writer.release()
        video_writer = None
    is_recording = False
    add_log(f"Recording saved: {recording_filename}")

# ======================================
# OBJECT TRACKING (for phones)
# ======================================

def update_phone_tracker(phones, persons, frame):
    global next_phone_id, phone_tracker
    current_time = time.time()
    for (fx1, fy1, fx2, fy2) in phones:
        cx = (fx1 + fx2) // 2
        cy = (fy1 + fy2) // 2
        centroid = (cx, cy)

        owner = None
        for px1, py1, px2, py2 in persons:
            if px1 <= cx <= px2 and py1 <= cy <= py2:
                owner = (px1, py1, px2, py2)
                break

        matched_id = None
        for pid, (prev_centroid, prev_time, prev_owner) in phone_tracker.items():
            if np.linalg.norm(np.array(centroid) - np.array(prev_centroid)) < 50:
                matched_id = pid
                break

        if matched_id is None:
            matched_id = next_phone_id
            next_phone_id += 1

        phone_tracker[matched_id] = (centroid, current_time, owner)

        if owner is not None:
            prev_owner = phone_tracker.get(matched_id, (None, None, None))[2]
            if prev_owner is not None and prev_owner != owner:
                trigger_alert("unknown", "Phone Passing", frame)
                phone_tracker[matched_id] = (centroid, current_time, owner)

    to_delete = [pid for pid, (_, t, _) in phone_tracker.items() if current_time - t > 5]
    for pid in to_delete:
        del phone_tracker[pid]

# ======================================
# HELPER: GROUP PERSONS INTO ROWS
# ======================================

def group_persons_by_row(persons, y_threshold=30):
    if not persons:
        return []
    persons_with_cy = [(p, (p[1] + p[3]) // 2) for p in persons]
    persons_with_cy.sort(key=lambda item: item[1])
    rows = []
    current_row = []
    current_avg_y = None
    for p, cy in persons_with_cy:
        if current_row:
            avg_y = sum((p2[1] + p2[3]) // 2 for p2 in current_row) // len(current_row)
            if abs(cy - avg_y) < y_threshold:
                current_row.append(p)
            else:
                current_row.sort(key=lambda q: (q[0] + q[2]) // 2)
                rows.append(current_row)
                current_row = [p]
        else:
            current_row.append(p)
    if current_row:
        current_row.sort(key=lambda q: (q[0] + q[2]) // 2)
        rows.append(current_row)
    return rows

# ======================================
# HELPER: COMPUTE GLOBAL SPACING
# ======================================

def compute_global_spacing(persons):
    rows = group_persons_by_row(persons, y_threshold=30)
    all_gaps = []
    for row in rows:
        if len(row) < 2:
            continue
        xs = [(p[0] + p[2]) // 2 for p in row]
        xs.sort()
        for i in range(len(xs)-1):
            all_gaps.append(xs[i+1] - xs[i])
    if not all_gaps:
        return 100  # fallback
    sorted_gaps = sorted(all_gaps)
    median = sorted_gaps[len(sorted_gaps)//2]
    return max(median, 10)

# ======================================
# HELPER: ASSIGN SEATS WITH A GIVEN OFFSET
# ======================================

def assign_seats_with_offset(row_persons, num_cols, global_spacing, offset):
    """
    returns (assignments, seat_xs)
    assignments: list of (person or None, col_idx)
    seat_xs: list of x-coordinate for each seat
    """
    if not row_persons:
        return [(None, i) for i in range(num_cols)], [offset + i*global_spacing for i in range(num_cols)]

    centers = [(p, (p[0] + p[2]) // 2) for p in row_persons]
    centers.sort(key=lambda x: x[1])  # sort by x

    assignments = []
    seat_xs = []
    
    # Keep track of which persons have been assigned
    assigned_indices = set()
    
    for col in range(num_cols):
        seat_x = offset + col * global_spacing
        seat_xs.append(seat_x)
        best_person = None
        best_dist = float('inf')
        best_idx = -1
        
        # Find the closest unassigned person to this seat
        for idx, (p, cx) in enumerate(centers):
            if idx in assigned_indices:
                continue
            dist = abs(cx - seat_x)
            # Use a wider tolerance (0.6 * spacing) to catch more students
            if dist < global_spacing * 0.6 and dist < best_dist:
                best_dist = dist
                best_person = p
                best_idx = idx
        
        if best_person is not None:
            assigned_indices.add(best_idx)
        
        assignments.append((best_person, col))
    
    # If all seats are filled but some persons remain unassigned (shouldn't happen),
    # we ignore them (they are likely duplicates or noise).
    return assignments, seat_xs

# ======================================
# PROCESS FRAME
# ======================================

def process_frame(frame):
    global current_absent_list, show_absent

    results = model(frame, conf=0.30)

    persons = []
    phones = []

    for result in results:
        for box in result.boxes:
            cls = int(box.cls[0])
            x1, y1, x2, y2 = map(int, box.xyxy[0])
            if cls == 0:
                persons.append((x1, y1, x2, y2))
            elif cls == 67:
                phones.append((x1, y1, x2, y2))

    # Group into rows
    person_rows = group_persons_by_row(persons, y_threshold=30)

    # Compute global spacing
    global_spacing = compute_global_spacing(persons)

    # Find the best global offset
    all_xs = []
    for row in person_rows:
        for p in row:
            all_xs.append((p[0] + p[2]) // 2)
    if all_xs:
        min_x = min(all_xs)
        max_x = max(all_xs)
    else:
        min_x = 0
        max_x = 100

    best_offset = None
    best_total_score = -1
    search_min = min_x - global_spacing * 2
    search_max = max_x + global_spacing * 2
    for offset in range(int(search_min), int(search_max + 1), 2):
        total_score = 0
        for row_idx, row in enumerate(person_rows):
            if row_idx >= len(seat_ids):
                break
            num_cols = len(seat_ids[row_idx])
            if not row:
                continue
            centers = [(p, (p[0] + p[2]) // 2) for p in row]
            for col in range(num_cols):
                seat_x = offset + col * global_spacing
                for p, cx in centers:
                    if abs(cx - seat_x) < global_spacing * 0.4:
                        total_score += 1
                        break
        if total_score > best_total_score:
            best_total_score = total_score
            best_offset = offset

    if best_offset is None:
        best_offset = min_x if all_xs else 0

    # Now assign seats
    suspicious_count = 0
    total_present = 0

    # Collect absent student IDs for logging
    absent_ids = []

    for row_idx, row in enumerate(person_rows):
        if row_idx >= len(seat_ids):
            break
        num_cols = len(seat_ids[row_idx])
        assignments, seat_xs = assign_seats_with_offset(row, num_cols, global_spacing, best_offset)

        if row:
            avg_y = sum((p[1] + p[3]) // 2 for p in row) // len(row)
        else:
            continue

        for col_idx, (person, _) in enumerate(assignments):
            student_id = seat_ids[row_idx][col_idx] if col_idx < len(seat_ids[row_idx]) else "Unknown"
            seat_x = seat_xs[col_idx]
            if seat_x is None:
                continue

            if person is not None:
                total_present += 1
                px1, py1, px2, py2 = person

                # Check phone
                suspicious = False
                for fx1, fy1, fx2, fy2 in phones:
                    cx_phone = (fx1 + fx2) // 2
                    cy_phone = (fy1 + fy2) // 2
                    if px1 <= cx_phone <= px2 and py1 <= cy_phone <= py2:
                        suspicious = True
                        break

                if suspicious:
                    trigger_alert(student_id, "Phone Detected", frame)
                    # --- CHANGED: suspicious box color from RED to BLUE ---
                    color = (0, 0, 255)       # BLUE
                    label = f"{student_id} Suspicious"
                    suspicious_count += 1
                else:
                    color = (0, 255, 0)       # GREEN
                    label = student_id

                cv2.rectangle(frame, (px1, py1), (px2, py2), color, 3)
                cv2.rectangle(frame, (px1, py1 - 35), (px1 + 220, py1), color, -1)
                cv2.putText(frame, label, (px1 + 10, py1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2)
            else:
                # Absent student
                absent_ids.append(student_id)
                if show_absent:
                    box_width = int(global_spacing * 0.8)
                    box_height = int(box_width * 1.2)
                    x1 = int(seat_x - box_width/2)
                    y1 = int(avg_y - box_height/2)
                    x2 = x1 + box_width
                    y2 = y1 + box_height
                    cv2.rectangle(frame, (x1, y1), (x2, y2), (128, 128, 128), 2)
                    label = f"{student_id} Absent"
                    text_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)[0]
                    text_x = x1 + (box_width - text_size[0]) // 2
                    text_y = y1 + (box_height + text_size[1]) // 2
                    cv2.putText(frame, label, (text_x, text_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (128, 128, 128), 2)

    # Update global absent list
    current_absent_list = absent_ids

    # Update counters
    student_count.configure(text=f"Students : {total_present}")
    suspicious_count_label.configure(text=f"Suspicious : {suspicious_count}")

    return frame

# ======================================
# UPLOAD IMAGE
# ======================================

def upload_image():
    file_path = filedialog.askopenfilename(
        filetypes=[("Image Files", "*.jpg *.png *.jpeg")]
    )
    if not file_path:
        return

    frame = cv2.imread(file_path)
    frame = process_frame(frame)

    frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    image = Image.fromarray(frame_rgb)
    image = image.resize((950, 650))
    ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(950, 650))
    camera_display.configure(image=ctk_image, text="")
    camera_display.image = ctk_image

    cv2.imwrite(f"screenshots/result_{int(time.time())}.jpg", frame)
    add_log("Uploaded image processed")

# ======================================
# UPDATE CAMERA LOOP
# ======================================

def update_camera():
    global running, frame_counter, last_processed_frame
    global is_recording, video_writer, recording_start_time
    global alert_active, alert_start_time
    global cap, current_camera_source

    if cap is None:
        app.after(10, update_camera)
        return

    ret, frame = cap.read()
    if not ret:
        add_log("Camera read failed, reconnecting...")
        if cap is not None:
            cap.release()
        cap = cv2.VideoCapture(current_camera_source)
        app.after(1000, update_camera)
        return

    if running:
        frame_counter += 1

        PROCESS_EVERY_N = 3
        if frame_counter % PROCESS_EVERY_N == 0 or last_processed_frame is None:
            processed = process_frame(frame)
            last_processed_frame = processed
        else:
            processed = last_processed_frame

        # Video Recording
        if is_recording:
            video_writer.write(processed)
            if time.time() - recording_start_time > RECORD_SECONDS:
                stop_recording()
        else:
            frame_buffer.append(processed.copy())

        # UI Alert flashing border
        if alert_active:
            if time.time() - alert_start_time > 2:
                alert_active = False
                video_frame.configure(border_width=0)

        # Display
        frame_rgb = cv2.cvtColor(processed, cv2.COLOR_BGR2RGB)
        image = Image.fromarray(frame_rgb)
        image = image.resize((950, 650))
        ctk_image = ctk.CTkImage(light_image=image, dark_image=image, size=(950, 650))
        camera_display.configure(image=ctk_image, text="")
        camera_display.image = ctk_image

    app.after(10, update_camera)

# ======================================
# START LOOP
# ======================================

update_camera()

# ======================================
# RUN APP
# ======================================

app.mainloop()

# ======================================
# RELEASE RESOURCES
# ======================================

cap.release()
cv2.destroyAllWindows()
if video_writer is not None:
    video_writer.release()