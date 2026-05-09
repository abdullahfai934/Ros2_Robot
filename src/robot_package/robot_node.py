#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
from nav_msgs.msg import Odometry
from geometry_msgs.msg import TransformStamped
from sensor_msgs.msg import JointState
from tf2_ros import TransformBroadcaster
import serial
import time
import math

class RobotNode(Node):
    def __init__(self):
        super().__init__('robot_node')

        # Publishers
        self.encoder_publisher     = self.create_publisher(String,    'esp32_encoders', 10)
        self.odom_publisher        = self.create_publisher(Odometry,  'odom',           10)
        self.joint_state_publisher = self.create_publisher(JointState,'joint_states',   10)
        self.tf_broadcaster        = TransformBroadcaster(self)

        # Subscriber
        self.create_subscription(String, 'esp32_commands', self.command_callback, 10)

        # Serial
        self.serial_port            = None
        self.port_name              = '/dev/ttyUSB0'
        self.baudrate               = 115200
        self.reconnect_interval     = 5.0
        self.last_reconnect_attempt = 0.0

        # Robot dimensions (GA25-370 motor, 2.7 in wheels, 7 in wheelbase)
        self.wheel_diameter     = 0.06858  # metres
        self.wheel_base         = 0.1778   # metres
        self.encoder_resolution = 374      # ticks/revolution

        # Pose
        self.x     = 0.0
        self.y     = 0.0
        self.theta = 0.0

        # Velocities
        self.linear_velocity  = 0.0
        self.angular_velocity = 0.0

        # Wheel angles for joint states visualisation
        self.left_wheel_angle  = 0.0
        self.right_wheel_angle = 0.0

        # Encoder tracking
        self.last_encoder_left  = 0
        self.last_encoder_right = 0
        self.last_odom_time     = self.get_clock().now()

        self.connect_serial()

        # ── Timers ────────────────────────────────────────────────────────
        # Read incoming serial at 50 Hz
        self.create_timer(0.02, self.read_encoder_values)

        # ✅ KEY FIX: Always publish TF + joint_states at 50 Hz.
        # Previously these were only published inside update_odometry(),
        # which only ran when ENCODER data arrived from ESP32.
        # If ESP32 sends no encoder data, the odom→base_link TF was never
        # broadcast and RViz showed nothing (incomplete TF tree).
        self.create_timer(0.02, self.publish_tf_and_joints)

    # ── Serial connection ─────────────────────────────────────────────────

    def connect_serial(self):
        try:
            if self.serial_port and self.serial_port.is_open:
                self.serial_port.close()
            self.serial_port = serial.Serial(
                self.port_name, self.baudrate,
                timeout=0.01, write_timeout=0.1)
            time.sleep(0.3)
            self.serial_port.reset_input_buffer()
            self.serial_port.reset_output_buffer()
            self.get_logger().info(
                f'Connected to {self.port_name} at {self.baudrate} baud')
            return True
        except serial.SerialException as e:
            self.get_logger().error(f'Cannot open serial port: {e}')
            self.serial_port = None
            return False
        except Exception as e:
            self.get_logger().error(f'Serial connect error: {e}')
            self.serial_port = None
            return False

    def _close_serial_quietly(self):
        try:
            if self.serial_port:
                self.serial_port.close()
        except Exception:
            pass
        self.serial_port = None

    def close_serial(self):
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
                self.get_logger().info('Serial port closed')
            except Exception:
                pass

    # ── Serial read loop ──────────────────────────────────────────────────

    def read_encoder_values(self):
        if not self.serial_port or not self.serial_port.is_open:
            now = time.time()
            if now - self.last_reconnect_attempt >= self.reconnect_interval:
                self.get_logger().warn('Serial disconnected — reconnecting...')
                self.last_reconnect_attempt = now
                self.connect_serial()
            return

        try:
            while self.serial_port.in_waiting:
                raw = self.serial_port.readline().decode('utf-8', errors='ignore').strip()
                if raw.startswith('ENCODER:'):
                    payload = raw[len('ENCODER:'):]

                    msg = String()
                    msg.data = payload
                    self.encoder_publisher.publish(msg)

                    parts = payload.split(',')
                    if len(parts) >= 2:
                        try:
                            self.update_odometry(
                                int(parts[0].strip()),
                                int(parts[1].strip()))
                        except ValueError:
                            pass

        except (serial.SerialException, OSError):
            self.get_logger().warn('Serial port lost')
            self._close_serial_quietly()
        except Exception as e:
            self.get_logger().error(f'Read error: {e}')
            self._close_serial_quietly()

    # ── Odometry calculation ──────────────────────────────────────────────

    def update_odometry(self, enc_left, enc_right):
        now = self.get_clock().now()
        dt  = (now - self.last_odom_time).nanoseconds / 1e9
        if dt < 0.001:
            return

        d_per_tick = (math.pi * self.wheel_diameter) / self.encoder_resolution

        # Sign convention: adjust if robot drives in wrong direction
        delta_right =  (enc_left  - self.last_encoder_left)
        delta_left  = -(enc_right - self.last_encoder_right)

        dist_left   = delta_left  * d_per_tick
        dist_right  = delta_right * d_per_tick
        dist_center = (dist_left + dist_right) / 2.0
        delta_theta = (dist_right - dist_left) / self.wheel_base

        if abs(delta_theta) < 1e-4:           # Straight line
            self.x += dist_center * math.cos(self.theta)
            self.y += dist_center * math.sin(self.theta)
        else:                                  # Arc
            r = dist_center / delta_theta
            self.x += r * (math.sin(self.theta + delta_theta) - math.sin(self.theta))
            self.y -= r * (math.cos(self.theta + delta_theta) - math.cos(self.theta))

        self.theta += delta_theta
        self.theta  = math.atan2(math.sin(self.theta), math.cos(self.theta))

        self.linear_velocity  = dist_center / dt
        self.angular_velocity = delta_theta  / dt

        # Absolute wheel angles for visualisation
        self.left_wheel_angle  = (enc_left  * d_per_tick) / (self.wheel_diameter / 2.0)
        self.right_wheel_angle = (enc_right * d_per_tick) / (self.wheel_diameter / 2.0)

        # Publish odometry message
        self._publish_odometry(now)

        self.last_encoder_left  = enc_left
        self.last_encoder_right = enc_right
        self.last_odom_time     = now

    def _publish_odometry(self, stamp):
        msg = Odometry()
        msg.header.stamp    = stamp.to_msg()
        msg.header.frame_id = 'odom'
        msg.child_frame_id  = 'base_link'

        msg.pose.pose.position.x = self.x
        msg.pose.pose.position.y = self.y
        msg.pose.pose.position.z = 0.0

        half = self.theta / 2.0
        msg.pose.pose.orientation.z = math.sin(half)
        msg.pose.pose.orientation.w = math.cos(half)

        msg.twist.twist.linear.x  = self.linear_velocity
        msg.twist.twist.angular.z = self.angular_velocity

        self.odom_publisher.publish(msg)

    # ── Always-on TF + joint state publisher ─────────────────────────────

    def publish_tf_and_joints(self):
        """
        Publish the odom→base_link TF transform and wheel joint states at
        50 Hz whether or not encoder data is arriving.

        This is the fix for the robot being invisible in RViz:
          • RViz's fixed frame is 'odom'
          • robot_state_publisher needs joint_states to compute
            base_link→left_wheel / right_wheel transforms
          • Both must arrive continuously or RViz drops the robot model
        """
        now = self.get_clock().now()

        # TF: odom → base_link
        t = TransformStamped()
        t.header.stamp    = now.to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id  = 'base_link'

        t.transform.translation.x = self.x
        t.transform.translation.y = self.y
        t.transform.translation.z = 0.0

        half = self.theta / 2.0
        t.transform.rotation.z = math.sin(half)
        t.transform.rotation.w = math.cos(half)

        self.tf_broadcaster.sendTransform(t)

        # Joint states: wheel rotations (for robot_state_publisher)
        js = JointState()
        js.header.stamp = now.to_msg()
        js.name         = ['left_wheel_joint', 'right_wheel_joint']
        js.position     = [-self.left_wheel_angle, self.right_wheel_angle]
        js.velocity     = []
        js.effort       = []
        self.joint_state_publisher.publish(js)

    # ── Command callback ──────────────────────────────────────────────────

    def command_callback(self, msg):
        if not self.serial_port or not self.serial_port.is_open:
            self.get_logger().warn('Cannot send command: serial not connected')
            return
        try:
            self.serial_port.write(f'{msg.data}\n'.encode('utf-8'))
            self.get_logger().info(f'Sent to ESP32: {msg.data}')
        except serial.SerialException as e:
            self.get_logger().error(f'Serial write error: {e}')
            self._close_serial_quietly()
        except Exception as e:
            self.get_logger().error(f'Write error: {e}')


def main(args=None):
    rclpy.init(args=args)
    node = RobotNode()

    print('\n' + '='*52)
    print('Robot Node Started')
    print('='*52)
    print('  Commands  ← /esp32_commands')
    print('  Encoders  → /esp32_encoders')
    print('  Odometry  → /odom')
    print('  TF        → odom → base_link  [always-on, 50 Hz]')
    print('  Joints    → /joint_states     [always-on, 50 Hz]')
    print(f'  Serial    → {node.port_name}')
    print('='*52 + '\n')

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close_serial()
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()