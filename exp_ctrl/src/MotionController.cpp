// Copyright (C) 2022 wngfra/captjulian
//
// tac3d is free software: you can redistribute it and/or modify
// it under the terms of the GNU Lesser General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// tac3d is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU Lesser General Public License for more details.
//
// You should have received a copy of the GNU Lesser General Public License
// along with tac3d. If not, see <http://www.gnu.org/licenses/>.
#include <math.h>

#include "exp_ctrl/MotionController.h"

using namespace std::chrono_literals;

namespace tac3d
{
    MotionController::MotionController(const std::string service_name) : Node("motion_controller_node")
    {
        m_client = this->create_client<control_interfaces::srv::Control2d>(service_name);
        while (!m_client->wait_for_service(std::chrono::seconds(1)))
        {
            if (!rclcpp::ok())
            {
                RCLCPP_ERROR(this->get_logger(), "Interrupted while waiting for the service. Exiting.");
                return;
            }
            RCLCPP_INFO(this->get_logger(), "service not available, waiting again...");
        }
        tactile_sub = this->create_subscription<sensor_msgs::msg::Image>(
            "/sensors/tactile_image", 10, std::bind(&MotionController::tactilePublisherCallback, this, std::placeholders::_1));
        start_time = this->now();
    }

    void MotionController::tactilePublisherCallback(const sensor_msgs::msg::Image::SharedPtr msg)
    {
        auto data = msg->data;
        double t = this->timeLapse().seconds();
        auto dx = cos(t)*2e-3;
        auto dy = sin(t)*2e-3;
        RCLCPP_INFO(this->get_logger(), "dx: %f, dy: %f", dx, dy);
        sendControlRequest(dx, dy);
    }

    void MotionController::sendControlRequest(const float dx, const float dy)
    {
        auto request = std::make_shared<control_interfaces::srv::Control2d::Request>();
        request->dx = dx;
        request->dy = dy;

        using ServiceResponseFuture =
            rclcpp::Client<control_interfaces::srv::Control2d>::SharedFutureWithRequest;
        auto responseReceivedCallback =
            [logger = this->get_logger()](ServiceResponseFuture future)
        {
            auto response = future.get();
        };
        auto result = m_client->async_send_request(request);
    }

    rclcpp::Duration MotionController::timeLapse()
    {
        return this->now() - start_time;
    }
} // namespace tac3d

int main(int argc, char **argv)
{
    rclcpp::init(argc, argv);
    auto node = std::make_shared<tac3d::MotionController>("/sim_ros2_interface/franka_control2d");
    rclcpp::executors::MultiThreadedExecutor executor;
    executor.add_node(node);
    executor.spin();
    rclcpp::shutdown();
    return 0;
}