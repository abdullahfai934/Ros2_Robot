#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import tkinter as tk
from tkinter import ttk
import threading

class ControlNode(Node):
    def __init__(self):
        super().__init__('control_node')
        
        self.command_publisher = self.create_publisher(String, 'esp32_commands', 10)
        
        self.encoder_subscriber = self.create_subscription(
            String,
            'esp32_encoders',
            self.encoder_callback,
            10
        )
        
        self.speed_value    = 50
        self.encoder1_value = 0
        self.encoder2_value = 0

        # ✅ FIX: Track active command so we can hold it
        self.current_command = 'stop'
        self.is_moving       = False

        self.get_logger().info('Control Node started')
    
    def encoder_callback(self, msg):
        try:
            parts = msg.data.split(',')
            if len(parts) >= 2:
                self.encoder1_value = int(parts[0].strip())
                self.encoder2_value = int(parts[1].strip())
        except (ValueError, IndexError):
            pass
    
    def send_command(self, command):
        msg = String()
        speed_pwm  = int((self.speed_value / 100.0) * 255)
        msg.data   = f"{command.lower()}:{speed_pwm}"
        self.command_publisher.publish(msg)
        self.get_logger().info(f'Sent command: {msg.data}')
        return msg.data

    # ✅ FIX: Toggle mode — click once to start moving, click again (or STOP) to stop
    def toggle_move(self, command, btn, all_buttons):
        if self.is_moving and self.current_command == command:
            # Already doing this command → stop
            self.is_moving       = False
            self.current_command = 'stop'
            self.send_command('stop')
            for b in all_buttons:
                b.config(relief=tk.RAISED)
        else:
            # Start this command
            self.is_moving       = True
            self.current_command = command
            self.send_command(command)
            for b in all_buttons:
                b.config(relief=tk.RAISED)
            btn.config(relief=tk.SUNKEN)

    def force_stop(self, all_buttons):
        self.is_moving       = False
        self.current_command = 'stop'
        self.send_command('stop')
        for b in all_buttons:
            b.config(relief=tk.RAISED)


def create_gui(node):
    root = tk.Tk()
    root.title("Robot Control")
    root.geometry("420x560")
    root.resizable(False, False)

    main_frame = ttk.Frame(root, padding="10")
    main_frame.pack(fill=tk.BOTH, expand=True)

    # ── Title ──────────────────────────────────────────────────────────────
    ttk.Label(main_frame, text="Robot Control", font=('Arial', 16, 'bold')).pack(pady=8)

    # ── Status bar ─────────────────────────────────────────────────────────
    status_var = tk.StringVar(value="Status: STOPPED")
    status_label = ttk.Label(main_frame, textvariable=status_var,
                             font=('Arial', 11), foreground='red')
    status_label.pack(pady=4)

    # ── Direction buttons ──────────────────────────────────────────────────
    ctrl_frame = ttk.Frame(main_frame)
    ctrl_frame.pack(pady=16)

    BTN_W, BTN_H = 10, 2
    FONT = ('Arial', 12, 'bold')

    fwd_btn  = tk.Button(ctrl_frame, text="▲  FORWARD", width=BTN_W, height=BTN_H,
                         bg='#4CAF50', fg='white', font=FONT)
    left_btn = tk.Button(ctrl_frame, text="◄  LEFT",    width=BTN_W, height=BTN_H,
                         bg='#2196F3', fg='white', font=FONT)
    stop_btn = tk.Button(ctrl_frame, text="■  STOP",    width=BTN_W, height=BTN_H,
                         bg='#f44336', fg='white', font=FONT)
    right_btn= tk.Button(ctrl_frame, text="RIGHT  ►",  width=BTN_W, height=BTN_H,
                         bg='#2196F3', fg='white', font=FONT)
    back_btn = tk.Button(ctrl_frame, text="▼  BACK",   width=BTN_W, height=BTN_H,
                         bg='#FF9800', fg='white', font=FONT)

    fwd_btn .grid(row=0, column=1, padx=5, pady=5)
    left_btn.grid(row=1, column=0, padx=5, pady=5)
    stop_btn.grid(row=1, column=1, padx=5, pady=5)
    right_btn.grid(row=1,column=2, padx=5, pady=5)
    back_btn.grid(row=2, column=1, padx=5, pady=5)

    move_btns = [fwd_btn, left_btn, right_btn, back_btn]

    # ✅ FIX: Toggle click — press once to go, press again or STOP to halt
    def make_toggle(cmd, btn):
        def handler():
            node.toggle_move(cmd, btn, move_btns)
            if node.is_moving:
                status_var.set(f"Status: {cmd.upper()}")
                status_label.config(foreground='green')
            else:
                status_var.set("Status: STOPPED")
                status_label.config(foreground='red')
        return handler

    fwd_btn .config(command=make_toggle('forward',  fwd_btn))
    left_btn.config(command=make_toggle('left',     left_btn))
    right_btn.config(command=make_toggle('right',   right_btn))
    back_btn.config(command=make_toggle('backward', back_btn))

    def on_stop():
        node.force_stop(move_btns)
        status_var.set("Status: STOPPED")
        status_label.config(foreground='red')

    stop_btn.config(command=on_stop)

    # ── Keyboard shortcuts ─────────────────────────────────────────────────
    # ✅ BONUS: Arrow keys also work (hold = continuous send every 100ms)
    key_held = {'key': None}

    def on_key_press(event):
        key_map = {
            'Up':    ('forward',  fwd_btn),
            'Down':  ('backward', back_btn),
            'Left':  ('left',     left_btn),
            'Right': ('right',    right_btn),
        }
        mapped = key_map.get(event.keysym)
        if mapped and key_held['key'] != event.keysym:
            key_held['key'] = event.keysym
            cmd, btn = mapped
            node.is_moving       = True
            node.current_command = cmd
            node.send_command(cmd)
            for b in move_btns:
                b.config(relief=tk.RAISED)
            btn.config(relief=tk.SUNKEN)
            status_var.set(f"Status: {cmd.upper()}")
            status_label.config(foreground='green')

    def on_key_release(event):
        key_map_keys = {'Up', 'Down', 'Left', 'Right'}
        if event.keysym in key_map_keys:
            key_held['key'] = None
            node.force_stop(move_btns)
            status_var.set("Status: STOPPED")
            status_label.config(foreground='red')

    root.bind('<KeyPress>',   on_key_press)
    root.bind('<KeyRelease>', on_key_release)
    root.bind('<space>', lambda e: on_stop())

    ttk.Label(main_frame,
              text="Click buttons to toggle | Arrow keys to drive | Space = STOP",
              font=('Arial', 8), foreground='gray').pack()

    # ── Speed control ──────────────────────────────────────────────────────
    spd_frame = ttk.LabelFrame(main_frame, text="Speed Control", padding="10")
    spd_frame.pack(fill=tk.X, pady=12)

    spd_val_lbl = ttk.Label(spd_frame, text="50%", font=('Arial', 14, 'bold'))
    spd_val_lbl.pack(pady=4)

    def update_speed(val):
        speed = int(float(val))
        node.speed_value = speed
        spd_val_lbl.config(text=f"{speed}%")
        # If currently moving, resend command at new speed immediately
        if node.is_moving:
            node.send_command(node.current_command)

    spd_slider = ttk.Scale(spd_frame, from_=0, to=100, orient=tk.HORIZONTAL,
                           length=320, command=update_speed)
    spd_slider.set(50)
    spd_slider.pack(pady=4)

    # ── Encoder display ────────────────────────────────────────────────────
    enc_frame = ttk.LabelFrame(main_frame, text="Encoder Values", padding="10")
    enc_frame.pack(fill=tk.X, pady=8)

    ttk.Label(enc_frame, text="Left  (Enc 1):", font=('Arial', 11)).grid(row=0, column=0, sticky=tk.W, pady=4)
    enc1_lbl = ttk.Label(enc_frame, text="0", font=('Arial', 11, 'bold'))
    enc1_lbl.grid(row=0, column=1, sticky=tk.W, padx=12, pady=4)

    ttk.Label(enc_frame, text="Right (Enc 2):", font=('Arial', 11)).grid(row=1, column=0, sticky=tk.W, pady=4)
    enc2_lbl = ttk.Label(enc_frame, text="0", font=('Arial', 11, 'bold'))
    enc2_lbl.grid(row=1, column=1, sticky=tk.W, padx=12, pady=4)

    # ── GUI update loop ────────────────────────────────────────────────────
    def update_gui():
        try:
            enc1_lbl.config(text=str(node.encoder1_value))
            enc2_lbl.config(text=str(node.encoder2_value))
            rclpy.spin_once(node, timeout_sec=0.001)
        except Exception as e:
            print(f"GUI update error: {e}")
        root.after(50, update_gui)

    # ── Clean shutdown ─────────────────────────────────────────────────────
    def on_closing():
        node.force_stop(move_btns)
        try:
            node.destroy_node()
        except Exception:
            pass
        # ✅ FIX: Guard against double-shutdown
        try:
            rclpy.shutdown()
        except Exception:
            pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    update_gui()
    return root


def main(args=None):
    rclpy.init(args=args)
    node = ControlNode()

    print("\n" + "="*50)
    print("Robot Control Node Started")
    print("="*50)
    print("\nOpening control GUI...")
    print("Click direction buttons to TOGGLE movement")
    print("Arrow keys: hold to move, release to stop")
    print("SPACE or STOP button = emergency stop")
    print("="*50 + "\n")

    root = create_gui(node)

    try:
        root.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            node.destroy_node()
        except Exception:
            pass
        # ✅ FIX: Guard against double-shutdown
        try:
            rclpy.shutdown()
        except Exception:
            pass

if __name__ == '__main__':
    main()