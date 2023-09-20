#include "gen/MainQuery.hpp"
#include "testframework.hpp"
#include "testutils.hpp"
#include <QSignalSpy>

namespace ScalarArguments {
using namespace qtgql;

auto ENV_NAME = std::string("ScalarArguments");
auto SCHEMA_ADDR = get_server_address(QString::fromStdString(ENV_NAME));

TEST_CASE("ScalarArguments") {
  auto env = test_utils::get_or_create_env(
      ENV_NAME, DebugClientSettings{.prod_settings = {.url = SCHEMA_ADDR}});
  auto mq = mainquery::MainQuery::shared();
  int int_exp = 123;
  float float_exp = 123.123;
  QString string_exp("foobar");
  auto uuid_exp = QUuid::createUuid();
  mq->set_variables({int_exp, float_exp, string_exp, false, uuid_exp});
  mq->fetch();
  test_utils::wait_for_completion(mq);
  auto container = mq->data()->get_getContainer();

  SECTION("test deserialize") {
    REQUIRE_EQ(container->get_i() , int_exp);
    REQUIRE_EQ(container->get_f() , float_exp);
    REQUIRE_EQ(container->get_string().toStdString() , string_exp.toStdString());
    REQUIRE_EQ(container->get_uuid().toString().toStdString() ,
            uuid_exp.toString().toStdString());
  };
  SECTION("test update") {
    auto nl = dynamic_cast<gqltransportws::GqlTransportWs *>(
        env->get_network_layer());
    // the server would scramble the object now; This is the easiest way to do
    // this since arguments would cache differently
    nl->set_headers({{{"NODE_ID"}, {container->get_id()}}});
    nl->reconnect();
    test_utils::SignalCatcher catcher({.source_obj = container});
    mq->refetch();
    REQUIRE(catcher.wait());
    test_utils::wait_for_completion(mq);
    REQUIRE_NE(container->get_i() , int_exp);
    REQUIRE_NE(container->get_f() , float_exp);
    REQUIRE_NE(container->get_string().toStdString() , string_exp.toStdString());
    REQUIRE_NE(container->get_uuid().toString().toStdString() ,
            uuid_exp.toString().toStdString());
  };
}

}; // namespace ScalarArguments